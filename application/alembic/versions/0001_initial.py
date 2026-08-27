"""initial schema: tools / agents / agent_tools / runs / run_steps + seed builtin tools

Revision ID: 0001
Revises:
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("type", sa.String(32), nullable=False, server_default="builtin"),
        sa.Column("description", sa.Text()),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("permission", sa.String(16), nullable=False, server_default="read"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_agents_tenant", "agents", ["tenant_id"])

    op.create_table(
        "agent_tools",
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tool_id", sa.String(64), sa.ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("user_id", sa.String(64)),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("token_usage", postgresql.JSONB()),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True)),
    )
    op.create_index("idx_runs_agent", "runs", ["agent_id", "created_at"])
    op.create_index("idx_runs_tenant", "runs", ["tenant_id", "created_at"])

    op.create_table(
        "run_steps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("node", sa.String(32), nullable=False),
        sa.Column("action", sa.String(128)),
        sa.Column("input", postgresql.JSONB()),
        sa.Column("output", postgresql.JSONB()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("token_usage", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_run_steps_run", "run_steps", ["run_id", "seq"])

    # Seed builtin tools (see §5 Tool Schema)
    tools_table = sa.table(
        "tools",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("type", sa.String),
        sa.column("description", sa.Text),
        sa.column("parameters", postgresql.JSONB),
        sa.column("permission", sa.String),
    )
    op.bulk_insert(
        tools_table,
        [
            {
                "id": "tool_calculator",
                "name": "calculator",
                "type": "builtin",
                "description": "Evaluate a math expression, supporting + - * / and parentheses",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": 'Math expression, e.g. "3*8+100"'}
                    },
                    "required": ["expression"],
                },
                "permission": "read",
            },
            {
                "id": "tool_http",
                "name": "http",
                "type": "builtin",
                "description": "Send an HTTP request and return the response, supporting GET/POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Request URL"},
                        "method": {"type": "string", "enum": ["GET", "POST"]},
                        "headers": {"type": "object"},
                        "body": {"type": "string"},
                    },
                    "required": ["url"],
                },
                "permission": "read",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("agent_tools")
    op.drop_table("agents")
    op.drop_table("tools")
