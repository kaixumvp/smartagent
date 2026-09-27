"""Postgres-backed run checkpoints (business adapter).

Implements the framework `Checkpointer` port (`ouroboros.ports`) over the `runs.checkpoint`
column. Storage has to outlive the request: a run that pauses on human approval is resumed
by a *different* HTTP request later, so the framework's in-process `InMemoryCheckpointer`
cannot be used here.
"""

import copy

from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import Run


class DbCheckpointer:
    """Persists the framework run state on the owning `runs` row.

    Uses the ORM rather than a Core UPDATE: the Run row is already in the session identity
    map (the route just created or loaded it), so `get` is a cache hit. The runtime
    checkpoints once per node, which is fine at V0.2 volumes.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(self, run_id: str, state: dict) -> None:
        run = await self._db.get(Run, run_id)
        if run is None:
            return
        # Deep-copy is load-bearing, not defensive: the runtime mutates one long-lived state
        # dict in place, so assigning it verbatim would (a) hand SQLAlchemy the same object
        # it already holds — no net attribute change, no UPDATE emitted — and (b) let later
        # mutations rewrite an already-saved snapshot.
        run.checkpoint = copy.deepcopy(state)
        await self._db.commit()

    async def load(self, run_id: str) -> dict | None:
        run = await self._db.get(Run, run_id)
        if run is None or run.checkpoint is None:
            return None
        return copy.deepcopy(run.checkpoint)

    async def delete(self, run_id: str) -> None:
        run = await self._db.get(Run, run_id)
        if run is None or run.checkpoint is None:
            return
        run.checkpoint = None
        await self._db.commit()
