"""Session consolidation: extract high-value fragments from Working Brain and store them in
Vector Memory (the Working → Cognitive step of the Brain lifecycle).

Rule-based extraction, ``Reflector``-based importance scoring, a forgetting threshold, and
similarity dedup. Each candidate is persisted best-effort so one failure does not abort the batch.
"""

import logging

from ouroboros.memory.reflect import Reflector
from ouroboros.ports import LongTermMemory

logger = logging.getLogger(__name__)


class Consolidator:
    """Turns a session's working history into durable Vector Memory entries.

    V0.3 adds `reflect`-based importance scoring and a forgetting threshold: candidates that
    score below `importance_threshold` are dropped at write time (never persisted).
    """

    def __init__(
        self,
        vector_store: LongTermMemory,
        similarity_threshold: float = 0.85,
        importance_threshold: float = 0.0,
        reflector: Reflector | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._threshold = similarity_threshold
        self._importance_threshold = importance_threshold
        self._reflector = reflector or Reflector()

    async def consolidate(
        self,
        db,
        session_id: str,
        tenant_id: str,
        user_id: str | None,
        history: list[dict],
    ) -> int:
        """Extract candidate fragments, score importance, dedup, and persist. Returns count inserted."""
        candidates = self._extract(history)
        inserted = 0
        for content in candidates:
            importance = self._reflector.score(content)
            if importance < self._importance_threshold:
                continue  # forgetting: drop low-value fragments before they reach memory
            try:
                existing = await self._vector_store.recall(db, tenant_id, user_id, content, top_k=1)
                if existing and (existing[0].similarity or 0.0) >= self._threshold:
                    continue  # near-duplicate already stored
                await self._vector_store.add(
                    db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id,
                    content=content,
                    importance=importance,
                )
            except Exception:  # noqa: BLE001 — memory persistence is best-effort
                logger.warning("consolidation failed for a candidate", exc_info=True)
                continue
            inserted += 1
        logger.debug("consolidated %d memories (session_id=%s)", inserted, session_id)
        return inserted

    def _extract(self, history: list[dict]) -> list[str]:
        """Rule-based extraction: keep user statements (facts/preferences) and the assistant's final answer."""
        candidates: list[str] = []
        last_assistant: str | None = None
        for message in history:
            role = message.get("role")
            content = (message.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                candidates.append(content)
            elif role == "assistant":
                last_assistant = content
        if last_assistant and last_assistant not in candidates:
            candidates.append(last_assistant)
        return candidates
