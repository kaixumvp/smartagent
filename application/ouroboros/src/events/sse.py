"""Deprecated (V0.3): the framework no longer serializes SSE.

``RuntimeEvent`` (see ``ouroboros.events``) is the framework's only output; SSE/WebSocket
serialization is the host's responsibility. This module is kept only so V0.2 imports keep
working, and ``SSEEvent.serialize`` remains as a convenience for hosts mid-migration.
"""

import json
import warnings

from src.events.events import (
    RuntimeEvent,
    run_approved,
    run_awaiting_human,
    run_completed,
    run_failed,
    run_rejected,
    run_started,
    step_completed,
)

warnings.warn(
    "src.events.sse is deprecated; use src.events (RuntimeEvent) and serialize on the host.",
    DeprecationWarning,
    stacklevel=2,
)


class SSEEvent(RuntimeEvent):
    def serialize(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False)
        return f"event: {self.event}\ndata: {payload}\n\n"


__all__ = [
    "SSEEvent",
    "run_started",
    "step_completed",
    "run_completed",
    "run_failed",
    "run_awaiting_human",
    "run_approved",
    "run_rejected",
]
