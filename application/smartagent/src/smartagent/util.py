"""Small cross-cutting primitives shared by routes, adapters, and services.

Kept deliberately tiny — id minting and "now" were being redefined per module, and the
`{prefix}_{uuid4hex}` convention is part of the persistence contract (see 业务层详细设计 §4.1),
so it belongs in one place.
"""

import uuid
from datetime import datetime, timezone


def new_id(prefix: str) -> str:
    """Mint an application-side primary key: `agent_`/`run_`/`step_`/`mem_`/… + uuid4 hex."""
    return f"{prefix}_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    """Timezone-aware current time (all TIMESTAMP columns are `timezone=True`)."""
    return datetime.now(timezone.utc)
