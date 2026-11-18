from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy.orm import Session

from . import models
from .embedding import Embedder
from .index import SearchFilter, VectorIndex
from .textutil import term_overlap, tokenize

QUOTE_RE = re.compile(r'"([^"]+)"|“([^”]+)”')
CODEISH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,}$")

# Retrieval modes: explicit override for the v0.2 A/B comparison
# (pure vector vs pure keyword vs hybrid fusion).
MODE_VECTOR = "vector"
MODE_KEYWORD = "keyword"
MODE_HYBRID = "hybrid"


@dataclass
class QueryAnalysis:
    query: str
    terms: list[str]
    quoted: list[str]
    strategy: str


def analyze_query(query: str) -> QueryAnalysis:
    quoted = [a or b for a, b in QUOTE_RE.findall(query)]
    terms = tokenize(query)
    stripped = query.strip()
    if quoted or (stripped and CODEISH_RE.match(stripped)):
        strategy = "keyword"
    elif len(terms) <= 2:
        strategy = "semantic"
    else:
        strategy = "hybrid"
    return QueryAnalysis(query=query, terms=terms, quoted=quoted, strategy=strategy)


def bm25_scores(query_tokens: list[str], texts: dict[str, str], k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    if not query_tokens or not texts:
        return {key: 0.0 for key in texts}
    tokenized = {key: tokenize(text) for key, text in texts.items()}
    avgdl = sum(len(toks) for toks in tokenized.values()) / max(len(tokenized), 1)
    df: dict[str, int] = defaultdict(int)
    qset = list(dict.fromkeys(query_tokens))
    for toks in tokenized.values():
        present = set(toks)
        for term in qset:
            if term in present:
                df[term] += 1
    n = len(tokenized)
    scores: dict[str, float] = {}
    for key, toks in tokenized.items():
        tf: dict[str, int] = defaultdict(int)
        for tok in toks:
            tf[tok] += 1
        score = 0.0
        dl = len(toks) or 1
        for term in qset:
            if tf[term] == 0:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            denom = tf[term] + k1 * (1 - b + b * dl / (avgdl or 1))
            score += idf * (tf[term] * (k1 + 1) / denom)
        scores[key] = score
    return scores


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranks in rank_lists:
        for i, chunk_id in enumerate(ranks):
            scores[chunk_id] += 1.0 / (k + i + 1)
    return dict(scores)


def _apply_filters(query, flt: SearchFilter):
    if flt.kb_ids:
        query = query.filter(models.Chunk.knowledge_base_id.in_(flt.kb_ids))
    if flt.folder_id:
        query = query.filter(models.Chunk.folder_id == flt.folder_id)
    if flt.mime_types:
        query = query.filter(models.Chunk.content_type.in_(flt.mime_types))
    if flt.created_after:
        query = query.filter(models.Chunk.created_at >= flt.created_after)
    if flt.created_before:
        query = query.filter(models.Chunk.created_at <= flt.created_before)
    return query


def lexical_rerank(query: QueryAnalysis, chunk_texts: dict[str, str], fused: dict[str, float]) -> dict[str, float]:
    out = {}
    for chunk_id, base in fused.items():
        overlap = term_overlap(query.terms, chunk_texts.get(chunk_id, ""))
        quote_bonus = 0.0
        text = chunk_texts.get(chunk_id, "").lower()
        for phrase in query.quoted:
            if phrase.lower() in text:
                quote_bonus += 0.25
        out[chunk_id] = base + 0.35 * overlap + quote_bonus
    return out


class Reranker(Protocol):
    def rerank(self, query: QueryAnalysis, chunk_texts: dict[str, str], fused: dict[str, float]) -> dict[str, float]: ...


class LexicalReranker:
    def rerank(self, query: QueryAnalysis, chunk_texts: dict[str, str], fused: dict[str, float]) -> dict[str, float]:
        return lexical_rerank(query, chunk_texts, fused)


class HttpCrossEncoder:
    """Optional cross-encoder reranker behind an HTTP endpoint.

    Contract: POST `{model, query, documents: [str, ...]}` → `{"scores": [float, ...]}`
    (higher = more relevant). Kept symmetric with `HttpEmbedder`.
    """

    def __init__(self, url: str, model: str = "reranker") -> None:
        self.url = url
        self.model = model

    def rerank(self, query: QueryAnalysis, chunk_texts: dict[str, str], fused: dict[str, float]) -> dict[str, float]:
        ids = list(fused.keys())
        if not ids:
            return {}
        documents = [chunk_texts.get(cid, "") for cid in ids]
        payload = {"model": self.model, "query": query.query, "documents": documents}
        with httpx.Client(timeout=60) as client:
            response = client.post(self.url, json=payload)
            response.raise_for_status()
            scores = response.json()["scores"]
        out: dict[str, float] = {}
        for cid, score in zip(ids, scores):
            out[cid] = fused[cid] + 0.5 * float(score)
        return out


def build_reranker(backend: str, url: str = "", model: str = "") -> Reranker:
    if backend in ("", "lexical", "none"):
        return LexicalReranker()
    if backend == "http":
        if not url:
            raise ValueError("RERANKER_URL is required when RERANKER_BACKEND=http")
        return HttpCrossEncoder(url, model or "reranker")
    raise ValueError(f"unknown reranker backend: {backend}")


def build_context(chunks: list[models.Chunk], filenames: dict[str, str], max_chars: int) -> str:
    parts: list[str] = []
    used = 0
    for chunk in chunks:
        name = filenames.get(chunk.document_id, chunk.document_id)
        heading = f" · {chunk.heading_path}" if chunk.heading_path else ""
        block = f"### {name}{heading} (chars {chunk.start_offset}-{chunk.end_offset})\n\n{chunk.text}\n"
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 80:
                parts.append(block[:remain] + "\n")
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts).strip()


class RetrievalService:
    def __init__(
        self,
        embedder: Embedder,
        index: VectorIndex,
        *,
        reranker: Reranker | None = None,
        candidate_multiplier: int = 4,
        rerank_enabled: bool = True,
        context_max_chars: int = 6000,
    ) -> None:
        self.embedder = embedder
        self.index = index
        self.reranker = reranker if reranker is not None else LexicalReranker()
        self.candidate_multiplier = candidate_multiplier
        self.rerank_enabled = rerank_enabled
        self.context_max_chars = context_max_chars

    def search(
        self,
        db: Session,
        query: str,
        flt: SearchFilter,
        top_k: int = 8,
        rerank: bool = True,
        mode: str = MODE_HYBRID,
    ) -> dict:
        analysis = analyze_query(query)
        pool = max(top_k * self.candidate_multiplier, top_k)

        dense_scores: dict[str, float] = {}
        dense_ranks: list[str] = []
        sparse: dict[str, float] = {}
        sparse_ranks: list[str] = []

        if mode != MODE_KEYWORD:
            vector = self.embedder.embed([query])[0]
            dense_hits = self.index.search(vector, pool, flt)
            dense_scores = {h.chunk_id: h.score for h in dense_hits}
            dense_ranks = [h.chunk_id for h in dense_hits]

        q = _apply_filters(db.query(models.Chunk), flt)
        rows: list[models.Chunk] = q.all()
        texts = {row.id: row.text for row in rows}

        if mode != MODE_VECTOR:
            sparse = bm25_scores(analysis.terms, texts)
            sparse_ranks = sorted(sparse, key=lambda cid: sparse[cid], reverse=True)[:pool]

        if mode == MODE_KEYWORD:
            fused = rrf_fuse([sparse_ranks])
        elif mode == MODE_VECTOR:
            fused = rrf_fuse([dense_ranks])
        else:
            fused = rrf_fuse([dense_ranks, sparse_ranks])

        rerank_applied = bool(rerank and self.rerank_enabled)
        if rerank_applied:
            final_scores = self.reranker.rerank(analysis, texts, fused)
        else:
            final_scores = fused

        ordered_ids = sorted(final_scores, key=lambda cid: final_scores[cid], reverse=True)[:top_k]
        by_id = {row.id: row for row in rows}
        selected = [by_id[cid] for cid in ordered_ids if cid in by_id]
        doc_ids = {c.document_id for c in selected}
        docs = {
            d.id: d
            for d in db.query(models.Document).filter(models.Document.id.in_(doc_ids)).all()
        } if doc_ids else {}
        filenames = {did: doc.filename for did, doc in docs.items()}
        hits = []
        for chunk in selected:
            hits.append(
                {
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "knowledge_base_id": chunk.knowledge_base_id,
                    "folder_id": chunk.folder_id,
                    "filename": filenames.get(chunk.document_id, ""),
                    "heading_path": chunk.heading_path,
                    "text": chunk.text,
                    "start_offset": chunk.start_offset,
                    "end_offset": chunk.end_offset,
                    "dense_score": float(dense_scores.get(chunk.id, 0.0)),
                    "sparse_score": float(sparse.get(chunk.id, 0.0)),
                    "fused_score": float(fused.get(chunk.id, 0.0)),
                    "rerank_score": float(final_scores.get(chunk.id, 0.0)),
                    "evidence": {
                        "document_id": chunk.document_id,
                        "filename": filenames.get(chunk.document_id, ""),
                        "start_offset": chunk.start_offset,
                        "end_offset": chunk.end_offset,
                        "heading_path": chunk.heading_path,
                    },
                }
            )
        return {
            "query": query,
            "analysis": {
                "query": analysis.query,
                "terms": analysis.terms,
                "quoted": analysis.quoted,
                "strategy": analysis.strategy,
            },
            "mode": mode,
            "rerank_applied": rerank_applied,
            "chunks": hits,
            "context": build_context(selected, filenames, self.context_max_chars),
        }
