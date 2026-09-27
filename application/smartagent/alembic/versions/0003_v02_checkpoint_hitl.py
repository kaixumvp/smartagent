"""V0.2 close-out: run checkpoint + mid-run HITL pending approvals.

Backs the framework `Checkpointer` port (ouroboros.ports) with Postgres so a run paused on
`awaiting_human` can be resumed in-place via `AgentRuntime.resume`, instead of the V0.2
pre-flight approval gate that re-ran the whole run.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Snapshot of the framework run state (ouroboros.core.state.AgentState). Written after
    # every node; cleared when the run reaches a terminal status.
    op.add_column("runs", sa.Column("checkpoint", postgresql.JSONB()))
    # Resources currently blocking the run on human approval, so GET /runs/{id} can echo them
    # back after the request that paused the run has ended.
    op.add_column("runs", sa.Column("pending_approvals", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("runs", "pending_approvals")
    op.drop_column("runs", "checkpoint")
