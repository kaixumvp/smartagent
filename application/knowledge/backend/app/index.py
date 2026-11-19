from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .textutil import l2_normalize


@dataclass
class VectorItem:
    chunk_id: str
    document_id: str
    knowledge_base_id: str
    folder_id: str | None
    content_type: str
    created_at: datetime
    vector: list[float]


@dataclass
class VectorHit:
    chunk_id: str
    score: float


@dataclass
class SearchFilter:
    kb_ids: list[str] = field(default_factory=list)
    folder_id: str | None = None
    mime_types: list[str] = field(default_factory=list)
    created_after: datetime | None = None
    created_before: datetime | None = None


def _matches(item: VectorItem, flt: SearchFilter) -> bool:
    if flt.kb_ids and item.knowledge_base_id not in flt.kb_ids:
        return False
    if flt.folder_id and item.folder_id != flt.folder_id:
        return False
    if flt.mime_types and item.content_type not in flt.mime_types:
        return False
    created = item.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=getattr(flt.created_after, "tzinfo", None))
    if flt.created_after and created < flt.created_after:
        return False
    if flt.created_before and created > flt.created_before:
        return False
    return True


def _dot(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


class VectorIndex(Protocol):
    def upsert(self, items: list[VectorItem]) -> None: ...
    def delete_document(self, document_id: str) -> None: ...
    def search(self, vector: list[float], top_k: int, flt: SearchFilter) -> list[VectorHit]: ...


class InMemoryVectorIndex:
    def __init__(self) -> None:
        self._items: dict[str, VectorItem] = {}

    def upsert(self, items: list[VectorItem]) -> None:
        for item in items:
            item.vector = l2_normalize(item.vector)
            self._items[item.chunk_id] = item

    def delete_document(self, document_id: str) -> None:
        dead = [k for k, v in self._items.items() if v.document_id == document_id]
        for key in dead:
            del self._items[key]

    def search(self, vector: list[float], top_k: int, flt: SearchFilter) -> list[VectorHit]:
        query = l2_normalize(vector)
        scored = [
            VectorHit(chunk_id=item.chunk_id, score=_dot(query, item.vector))
            for item in self._items.values()
            if _matches(item, flt)
        ]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


class QdrantVectorIndex:
    def __init__(self, url: str, collection: str, dim: int) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        self._qm = qm
        self.client = QdrantClient(url=url)
        self.collection = collection
        self.dim = dim
        existing = {c.name for c in self.client.get_collections().collections}
        if collection not in existing:
            self.client.create_collection(
                collection_name=collection,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )

    def upsert(self, items: list[VectorItem]) -> None:
        if not items:
            return
        points = []
        for item in items:
            points.append(
                self._qm.PointStruct(
                    id=_stable_uuid(item.chunk_id),
                    vector=item.vector,
                    payload={
                        "chunk_id": item.chunk_id,
                        "document_id": item.document_id,
                        "knowledge_base_id": item.knowledge_base_id,
                        "folder_id": item.folder_id,
                        "content_type": item.content_type,
                        "created_at": item.created_at.isoformat() if item.created_at else None,
                    },
                )
            )
        self.client.upsert(collection_name=self.collection, points=points)

    def delete_document(self, document_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=self._qm.FilterSelector(
                filter=self._qm.Filter(
                    must=[
                        self._qm.FieldCondition(
                            key="document_id",
                            match=self._qm.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

    def search(self, vector: list[float], top_k: int, flt: SearchFilter) -> list[VectorHit]:
        must = []
        if flt.kb_ids:
            must.append(
                self._qm.FieldCondition(
                    key="knowledge_base_id",
                    match=self._qm.MatchAny(any=flt.kb_ids),
                )
            )
        if flt.folder_id:
            must.append(
                self._qm.FieldCondition(
                    key="folder_id",
                    match=self._qm.MatchValue(value=flt.folder_id),
                )
            )
        if flt.mime_types:
            must.append(
                self._qm.FieldCondition(
                    key="content_type",
                    match=self._qm.MatchAny(any=flt.mime_types),
                )
            )
        qfilter = self._qm.Filter(must=must) if must else None
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            limit=top_k,
            query_filter=qfilter,
        )
        hits = []
        for point in results:
            created = (point.payload or {}).get("created_at")
            if flt.created_after or flt.created_before:
                if not created:
                    continue
                stamp = datetime.fromisoformat(created)
                if flt.created_after and stamp < flt.created_after:
                    continue
                if flt.created_before and stamp > flt.created_before:
                    continue
            hits.append(VectorHit(chunk_id=point.payload["chunk_id"], score=float(point.score)))
        return hits


def _stable_uuid(chunk_id: str) -> str:
    import hashlib
    import uuid

    digest = hashlib.md5(chunk_id.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest))


def build_index(qdrant_url: str, collection: str, dim: int) -> VectorIndex:
    if qdrant_url:
        return QdrantVectorIndex(qdrant_url, collection, dim)
    return InMemoryVectorIndex()
