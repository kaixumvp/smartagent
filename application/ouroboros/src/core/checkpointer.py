"""Zero-dependency in-memory Checkpointer (V0.3).

Used by tests and single-process deployments. Production hosts should implement the
``ouroboros.ports.Checkpointer`` protocol over Redis/Postgres/etc. and pass it via
``RuntimeDeps.checkpointer``.
"""

from __future__ import annotations

import copy

from src.ports import Checkpointer


class InMemoryCheckpointer:
    """Stores run state keyed by ``run_id``. State is deep-copied on save/load so the
    runtime's later mutations never corrupt a saved snapshot."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def save(self, run_id: str, state: dict) -> None:
        self._store[run_id] = copy.deepcopy(state)

    async def load(self, run_id: str) -> dict | None:
        state = self._store.get(run_id)
        return copy.deepcopy(state) if state is not None else None

    async def delete(self, run_id: str) -> None:
        self._store.pop(run_id, None)

    async def list_runs(self) -> list[str]:
        return list(self._store)


# Re-export the protocol alongside the default implementation for convenience.
__all__ = ["InMemoryCheckpointer", "Checkpointer"]
