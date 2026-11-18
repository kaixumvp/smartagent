from app import models
from app.embedding import HashEmbedder
from app.ids import utcnow
from app.index import InMemoryVectorIndex, SearchFilter, VectorItem
from app.retrieval import (
    QueryAnalysis,
    RetrievalService,
    analyze_query,
    bm25_scores,
    lexical_rerank,
    rrf_fuse,
)


def test_analyze_query_strategies():
    assert analyze_query('"exact code"').strategy == "keyword"
    assert analyze_query("XK-4021").strategy == "keyword"
    assert analyze_query("revenue").strategy == "keyword"  # single bare token
    assert analyze_query("hello world").strategy == "semantic"
    assert analyze_query("quarterly revenue growth").strategy == "hybrid"


def test_bm25_ranks_keyword_match_first():
    texts = {"a": "The lunch menu has pizza", "b": "Quarterly revenue revenue revenue"}
    scores = bm25_scores(["revenue"], texts)
    assert scores["b"] > scores["a"]


def test_bm25_empty_query_zeroes():
    scores = bm25_scores([], {"a": "x", "b": "y"})
    assert scores == {"a": 0.0, "b": 0.0}


def test_rrf_fuse_reversed_lists_tie():
    fused = rrf_fuse([["a", "b"], ["b", "a"]])
    assert abs(fused["a"] - fused["b"]) < 1e-9


def test_lexical_rerank_rewards_overlap():
    q = QueryAnalysis("revenue growth", ["revenue", "growth"], [], "hybrid")
    texts = {"a": "revenue grew 20 percent", "b": "nothing relevant here"}
    fused = {"a": 0.01, "b": 0.01}
    out = lexical_rerank(q, texts, fused)
    assert out["a"] > out["b"]


def _seed(session):
    kb = models.KnowledgeBase(id="kb_1", name="x")
    doc = models.Document(
        id="doc_1",
        knowledge_base_id="kb_1",
        filename="report.md",
        content_type="text/markdown",
        status="ready",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    chunks = [
        models.Chunk(
            id="c1",
            document_id="doc_1",
            knowledge_base_id="kb_1",
            ordinal=0,
            text="Quarterly revenue grew 20 percent in Q3.",
            start_offset=0,
            end_offset=44,
            content_type="text/markdown",
            created_at=utcnow(),
        ),
        models.Chunk(
            id="c2",
            document_id="doc_1",
            knowledge_base_id="kb_1",
            ordinal=1,
            text="The lunch menu features pizza and salad.",
            start_offset=45,
            end_offset=90,
            content_type="text/markdown",
            created_at=utcnow(),
        ),
    ]
    session.add_all([kb, doc, *chunks])
    session.commit()
    return doc, chunks


def _populated_service(chunks):
    embedder = HashEmbedder(256)
    index = InMemoryVectorIndex()
    index.upsert(
        [
            VectorItem(
                chunk_id=c.id,
                document_id=c.document_id,
                knowledge_base_id=c.knowledge_base_id,
                folder_id=c.folder_id,
                content_type=c.content_type,
                created_at=c.created_at,
                vector=embedder.embed([c.text])[0],
            )
            for c in chunks
        ]
    )
    return embedder, index, RetrievalService(embedder, index)


def test_search_end_to_end(session):
    doc, chunks = _seed(session)
    _, _, svc = _populated_service(chunks)
    res = svc.search(session, "revenue growth", SearchFilter(kb_ids=["kb_1"]), top_k=2)
    assert res["mode"] == "hybrid"
    assert res["rerank_applied"] is True
    assert res["chunks"][0]["text"].startswith("Quarterly revenue")
    assert res["chunks"][0]["evidence"]["document_id"] == "doc_1"
    assert res["chunks"][0]["start_offset"] == 0
    assert "Quarterly revenue" in res["context"]


def test_keyword_mode_ranks_term_match(session):
    _, chunks = _seed(session)
    embedder, _, _ = _populated_service(chunks)
    svc = RetrievalService(embedder, InMemoryVectorIndex())
    res = svc.search(session, "pizza", SearchFilter(kb_ids=["kb_1"]), top_k=1, mode="keyword")
    assert res["chunks"][0]["text"].startswith("The lunch menu")


def test_vector_mode_does_not_require_sparse(session):
    _, chunks = _seed(session)
    _, _, svc = _populated_service(chunks)
    res = svc.search(session, "revenue", SearchFilter(kb_ids=["kb_1"]), top_k=1, mode="vector")
    assert res["chunks"][0]["text"].startswith("Quarterly revenue")
    assert res["chunks"][0]["sparse_score"] == 0.0
