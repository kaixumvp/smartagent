"""add API services and HTTP-backed tools

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("auth_type", sa.String(40), nullable=False, server_default="none"),
        sa.Column("auth_config_encrypted", sa.Text(), nullable=True),
        sa.Column("allow_private_network", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("request_timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "tools",
        sa.Column("api_service_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tools_api_service_id",
        "tools",
        "api_services",
        ["api_service_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tools_api_service_id", "tools", type_="foreignkey")
    op.drop_column("tools", "api_service_id")
    op.drop_table("api_services")
