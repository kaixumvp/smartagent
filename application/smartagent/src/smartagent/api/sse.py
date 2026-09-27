"""Server-Sent Events serialization (host-side).

The framework produces `RuntimeEvent` objects and nothing else — transport is the host's
concern, and `ouroboros.events.sse` is deprecated (it warns on import). Keeping the wire
format here gives the event contract in 《API文档.md》§11 exactly one implementation.
"""

import json


def to_sse(event) -> str:
    """Render a `ouroboros.events.events.RuntimeEvent` as one SSE frame."""
    payload = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n"
