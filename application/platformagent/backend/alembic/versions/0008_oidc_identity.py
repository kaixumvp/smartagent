"""Add tenant-configured OIDC providers, identity links, and single-use auth transactions.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "identity_providers",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=256), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_by", sa.String(length=64)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_identity_providers_key",
        "identity_providers",
        ["tenant_id", "provider_key"],
        unique=True,
    )

    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider_id",
            sa.String(length=64),
            sa.ForeignKey("identity_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email_snapshot", sa.String(length=320)),
        sa.Column("display_name_snapshot", sa.String(length=128)),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("linked_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        "uq_external_identities_subject",
        "external_identities",
        ["provider_id", "issuer", "subject"],
        unique=True,
    )
    op.create_index("idx_external_identities_user", "external_identities", ["tenant_id", "user_id"])

    op.create_table(
        "oidc_transactions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "provider_id",
            sa.String(length=64),
            sa.ForeignKey("identity_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("pkce_verifier_encrypted", sa.Text(), nullable=False),
        sa.Column("browser_binding_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "link_user_id",
            sa.String(length=64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_oidc_transactions_state_hash", "oidc_transactions", ["state_hash"], unique=True)
    op.create_index("idx_oidc_transactions_expiry", "oidc_transactions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("oidc_transactions")
    op.drop_table("external_identities")
    op.drop_table("identity_providers")
