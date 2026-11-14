"""Memory Manager facade: host-side memory orchestration.

Delegates write / recall / consolidate to the Working Memory (short-term) and Long-Term
Memory (long-term) ports plus a Consolidator. The runtime itself calls the ``LongTermMemory``
and ``Knowledge`` ports directly; hosts use this facade to write session history and
consolidate it into long-term memory.
"""

from ouroboros.memory.consolidator import Consolidator
from ouroboros.ports import LongTermMemory, MemoryEntry, WorkingMemory


class MemoryManager:
    """Facade over Working Brain (short-term) and Long-Term Memory (long-term)."""

    def __init__(
        self,
        working: WorkingMemory,
        vector_store: LongTermMemory,
        consolidator: Consolidator,
    ) -> None:
        self._working = working
        self._vector_store = vector_store
        self._consolidator = consolidator

    async def write(self, session_id: str, message: dict) -> None:
        """Write into the Working Brain (session-scoped, TTL)."""
        await self._working.append(session_id, message)

    async def get_history(self, session_id: str) -> list[dict]:
        """Read the session's Working Brain history."""
        return await self._working.get_history(session_id)

    async def recall(
        self,
        db,
        tenant_id: str,
        user_id: str | None,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Recall semantically similar long-term memories."""
        return await self._vector_store.recall(db, tenant_id, user_id, query, top_k)

    async def consolidate(self, db, session_id: str, tenant_id: str, user_id: str | None) -> int:
        """Persist the session's high-value fragments into Long-Term Memory (best-effort)."""
        history = await self._working.get_history(session_id)
        if not history:
            return 0
        return await self._consolidator.consolidate(db, session_id, tenant_id, user_id, history)
