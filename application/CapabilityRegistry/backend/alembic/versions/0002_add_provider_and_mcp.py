"""add providers table and extend tools for MCP

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("credential_ref", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="offline"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("tools", sa.Column("source", sa.String(20), nullable=False, server_default="local"))
    op.add_column("tools", sa.Column("remote_tool_name", sa.String(255), nullable=True))
    op.add_column("tools", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("tools", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tools",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tools_provider_id", "tools", "providers", ["provider_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_tools_provider_id", "tools", type_="foreignkey")
    op.drop_column("tools", "provider_id")
    op.drop_column("tools", "last_synced_at")
    op.drop_column("tools", "enabled")
    op.drop_column("tools", "remote_tool_name")
    op.drop_column("tools", "source")
    op.drop_table("providers")
