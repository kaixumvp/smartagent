"""Runtime event model (V0.3).

The framework only *produces* ``RuntimeEvent`` objects; transport (SSE, WebSocket, …) is
the host's responsibility. An ``EventSink`` port (``ouroboros.ports.EventSink``) receives
these objects via ``RuntimeDeps.event_sink``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimeEvent(BaseModel):
    event: str
    data: dict = Field(default_factory=dict)
    run_id: str | None = None


def run_started(run_id: str) -> RuntimeEvent:
    return RuntimeEvent(event="run.started", run_id=run_id, data={"run_id": run_id, "status": "running"})


def step_completed(step) -> RuntimeEvent:
    # Accepts either a Step model or a plain dict (duck-typed to avoid importing core).
    if hasattr(step, "model_dump"):
        step = step.model_dump()
    return RuntimeEvent(
        event="step.completed",
        run_id=step.get("run_id"),
        data={
            "seq": step.get("seq"),
            "node": step.get("node"),
            "action": step.get("action"),
            "output": step.get("output"),
            "latency_ms": step.get("latency_ms"),
        },
    )


def run_completed(run_id: str, result: str | None, usage: dict) -> RuntimeEvent:
    return RuntimeEvent(
        event="run.completed",
        run_id=run_id,
        data={"run_id": run_id, "status": "completed", "result": result, "usage": usage},
    )


def run_failed(run_id: str, error: str) -> RuntimeEvent:
    return RuntimeEvent(
        event="run.failed",
        run_id=run_id,
        data={"run_id": run_id, "status": "failed", "error": error},
    )


def run_awaiting_human(run_id: str, pending_approvals: list[dict]) -> RuntimeEvent:
    return RuntimeEvent(
        event="run.awaiting_human",
        run_id=run_id,
        data={"run_id": run_id, "status": "awaiting_human", "pending_approvals": pending_approvals},
    )


def run_approved(run_id: str) -> RuntimeEvent:
    return RuntimeEvent(event="run.approved", run_id=run_id, data={"run_id": run_id, "status": "running"})


def run_rejected(run_id: str) -> RuntimeEvent:
    return RuntimeEvent(event="run.rejected", run_id=run_id, data={"run_id": run_id, "status": "canceled"})


__all__ = [
    "RuntimeEvent",
    "run_started",
    "step_completed",
    "run_completed",
    "run_failed",
    "run_awaiting_human",
    "run_approved",
    "run_rejected",
]
