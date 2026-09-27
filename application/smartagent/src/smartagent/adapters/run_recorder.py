"""Run timeline recorder (business adapter).

Implements the framework `EventSink` port (`ouroboros.ports`). The framework only *produces*
`RuntimeEvent` objects; deciding that they mean "write a row" or "push an SSE frame" is the
host's job, and this is where that decision lives.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import Run, RunStep
from smartagent.util import new_id, utcnow

logger = logging.getLogger(__name__)

# Events that carry a run's terminal (or paused) disposition.
_TERMINAL_EVENTS = {"run.completed", "run.failed", "run.awaiting_human"}


class RunRecorder:
    """Persists one run's steps and terminal state, optionally fanning events out to a queue.

    Scope is a single run on purpose: every sub-agent run needs its own recorder, otherwise
    the child's steps would be attributed to the parent run.

    This is the *only* write path for `run_steps` — do not additionally persist
    `RunResult.steps` after the run, or every step lands twice.
    """

    def __init__(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        queue: asyncio.Queue | None = None,
        seq_offset: int = 0,
    ) -> None:
        self._db = db
        self._run_id = run_id
        self._queue = queue
        # The framework restarts its step counter at 1 for every `run()`/`resume()` call, but
        # `run_steps.seq` is the position in the *run's whole timeline* — so a resumed run has
        # to continue numbering where it paused, or the ordering index collides.
        self._seq_offset = seq_offset
        self._last_step: RunStep | None = None

    async def __call__(self, event) -> None:
        try:
            if event.event == "step.completed":
                await self._record_step(event.data or {})
            elif event.event in _TERMINAL_EVENTS:
                await self._record_terminal(event.event, event.data or {})
        except Exception:  # noqa: BLE001 — never let bookkeeping abort a run in progress
            logger.exception("run recorder failed: run_id=%s event=%s", self._run_id, event.event)
            await self._db.rollback()

        # Emitted after persistence so an SSE client never observes a step that is not durable.
        if self._queue is not None:
            await self._queue.put(event)

    async def _record_step(self, data: dict) -> None:
        step = RunStep(
            id=new_id("step"),
            run_id=self._run_id,
            seq=(data.get("seq") or 0) + self._seq_offset,
            node=data.get("node"),
            action=data.get("action"),
            output=data.get("output"),
            status="success",
            latency_ms=data.get("latency_ms"),
        )
        self._db.add(step)
        await self._db.commit()
        self._last_step = step

    async def _record_terminal(self, name: str, data: dict) -> None:
        run = await self._db.get(Run, self._run_id)
        if run is None:
            return

        run.status = data.get("status") or run.status
        if "result" in data:
            run.result = data.get("result")
        if "error" in data:
            run.error = data.get("error")
        if data.get("usage"):
            run.token_usage = data["usage"]

        if name == "run.awaiting_human":
            run.pending_approvals = data.get("pending_approvals") or []
            # `step.completed` carries no status field, so the paused step was written as
            # "success" a moment ago. The pause always follows its own execute step, so the
            # most recent one is the blocked step — correct it here.
            if self._last_step is not None:
                self._last_step.status = "awaiting_human"
        else:
            run.pending_approvals = None
            run.finished_at = utcnow()

        await self._db.commit()
