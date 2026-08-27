"""Vector Memory: semantic long-term memory backed by pgvector (business adapter).

Implements the framework `LongTermMemory` port. The embedding column is never selected on
read; similarity is computed SQL-side via cosine_distance so no asyncpg vector type
registration is required for reads.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import VectorMemory
from smartagent.util import new_id
from ouroboros.llm.embedder import Embedder
from ouroboros.ports import MemoryEntry


class VectorMemoryStore:
    """Writes and recalls VectorMemory rows against a caller-provided AsyncSession."""

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    async def add(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        user_id: str | None,
        session_id: str | None,
        content: str,
        importance: float = 0.5,
        confidence: float = 0.5,
    ) -> str:
        embedding = (await self._embedder.embed([content]))[0]
        mem = VectorMemory(
            id=new_id("mem"),
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            content=content,
            embedding=embedding,
            importance=importance,
            confidence=confidence,
        )
        db.add(mem)
        await db.commit()
        return mem.id

    async def recall(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str | None,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        embedding = (await self._embedder.embed([query]))[0]
        distance = VectorMemory.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(
                VectorMemory.id,
                VectorMemory.tenant_id,
                VectorMemory.user_id,
                VectorMemory.session_id,
                VectorMemory.content,
                VectorMemory.importance,
                VectorMemory.confidence,
                VectorMemory.created_at,
                distance,
            )
            .where(VectorMemory.tenant_id == tenant_id)
            .order_by(distance)
            .limit(top_k)
        )
        if user_id is not None:
            stmt = stmt.where(VectorMemory.user_id == user_id)

        rows = (await db.execute(stmt)).all()
        entries: list[MemoryEntry] = []
        for row in rows:
            entries.append(
                MemoryEntry(
                    id=row[0],
                    tenant_id=row[1],
                    user_id=row[2],
                    session_id=row[3],
                    content=row[4],
                    importance=float(row[5]),
                    confidence=float(row[6]),
                    created_at=row[7],
                    similarity=1.0 - float(row[8]),
                )
            )
        return entries
