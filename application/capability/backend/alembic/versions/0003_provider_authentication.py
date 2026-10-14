"""add encrypted MCP Provider authentication configuration

Revision ID: 0003
Revises: 0002
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_SECRET_QUERY_NAMES = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "password",
    "secret",
    "token",
}


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("auth_type", sa.String(40), nullable=False, server_default="none"),
    )
    op.add_column("providers", sa.Column("auth_config_encrypted", sa.Text(), nullable=True))

    from app.mcp_auth import encrypt_auth_config
    from app.config import settings

    bind = op.get_bind()
    providers = bind.execute(sa.text("SELECT id, endpoint FROM providers")).mappings()
    for provider in providers:
        parsed = urlsplit(provider["endpoint"])
        query = parse_qsl(parsed.query, keep_blank_values=True)
        secret_params = {
            name: value for name, value in query if name.lower() in _SECRET_QUERY_NAMES
        }
        if not secret_params:
            continue
        if not settings.mcp_auth_encryption_key:
            raise RuntimeError(
                "MCP_AUTH_ENCRYPTION_KEY is required to migrate Provider credentials "
                "from endpoint query strings"
            )

        public_query = [(name, value) for name, value in query if name not in secret_params]
        endpoint = urlunsplit(parsed._replace(query=urlencode(public_query)))
        encrypted = encrypt_auth_config({"query_params": secret_params})
        bind.execute(
            sa.text(
                "UPDATE providers SET endpoint = :endpoint, auth_type = :auth_type, "
                "auth_config_encrypted = :encrypted WHERE id = :id"
            ),
            {
                "id": provider["id"],
                "endpoint": endpoint,
                "auth_type": "custom_query_params",
                "encrypted": encrypted,
            },
        )


def downgrade() -> None:
    from app.mcp_auth import decrypt_auth_config

    bind = op.get_bind()
    providers = bind.execute(
        sa.text(
            "SELECT id, endpoint, auth_type, auth_config_encrypted FROM providers "
            "WHERE auth_type = 'custom_query_params' AND auth_config_encrypted IS NOT NULL"
        )
    ).mappings()
    for provider in providers:
        config = decrypt_auth_config(provider["auth_config_encrypted"])
        parsed = urlsplit(provider["endpoint"])
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.extend(config.get("query_params", {}).items())
        bind.execute(
            sa.text("UPDATE providers SET endpoint = :endpoint WHERE id = :id"),
            {
                "id": provider["id"],
                "endpoint": urlunsplit(parsed._replace(query=urlencode(query))),
            },
        )
    op.drop_column("providers", "auth_config_encrypted")
    op.drop_column("providers", "auth_type")
