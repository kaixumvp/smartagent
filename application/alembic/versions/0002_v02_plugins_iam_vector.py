"""V0.2: multi-tenancy, IAM, skills, long-term vector memory, audit log, tool/runs extensions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# --------------------------------------------------------------------------- tables
def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("quota", postgresql.JSONB()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_users_tenant_username", "users", ["tenant_id", "username"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_roles_tenant_name", "roles", ["tenant_id", "name"], unique=True)

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.String(64), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(64), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.String(64), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("principal_type", sa.String(16), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(16), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("effect", sa.String(8), nullable=False, server_default="allow"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_grants_principal", "grants", ["tenant_id", "principal_type", "principal_id"])
    op.create_index("idx_grants_resource", "grants", ["tenant_id", "resource_type", "resource_id"])

    op.create_table(
        "skills",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("manifest", postgresql.JSONB(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("owner", sa.String(64)),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_skills_tenant_name_ver", "skills", ["tenant_id", "name", "version"], unique=True)
    op.create_index("idx_skills_latest", "skills", ["tenant_id", "name"], postgresql_where=sa.text("is_latest"))

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "vector_memories",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64)),
        sa.Column("session_id", sa.String(64)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("importance", sa.Numeric(6, 3), nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Numeric(6, 3), nullable=False, server_default="0.5"),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_access", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("ttl", postgresql.TIMESTAMP(timezone=True)),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_vecmem_tenant_user", "vector_memories", ["tenant_id", "user_id"])
    op.execute("CREATE INDEX idx_vecmem_embedding ON vector_memories USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64)),
        sa.Column("actor", sa.String(64)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(16)),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("detail", postgresql.JSONB()),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_tenant_time", "audit_logs", ["tenant_id", "created_at"])

    # --- alter existing tables ---
    op.add_column("tools", sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"))
    op.add_column("tools", sa.Column("endpoint", sa.Text()))
    op.add_column("tools", sa.Column("config", postgresql.JSONB()))
    op.add_column("tools", sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("tools", sa.Column("owner", sa.String(64)))
    op.create_index("idx_tools_tenant", "tools", ["tenant_id"])

    op.add_column("runs", sa.Column("approvals", postgresql.JSONB()))
    op.add_column("runs", sa.Column("parent_run_id", sa.String(64), sa.ForeignKey("runs.id")))
    op.create_index("idx_runs_parent", "runs", ["parent_run_id"])

    _seed()


def downgrade() -> None:
    op.drop_index("idx_runs_parent", table_name="runs")
    op.drop_column("runs", "parent_run_id")
    op.drop_column("runs", "approvals")
    op.drop_index("idx_tools_tenant", table_name="tools")
    op.drop_column("tools", "owner")
    op.drop_column("tools", "requires_approval")
    op.drop_column("tools", "config")
    op.drop_column("tools", "endpoint")
    op.drop_column("tools", "tenant_id")
    op.drop_table("audit_logs")
    op.drop_table("vector_memories")
    op.drop_table("skills")
    op.drop_table("grants")
    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("tenants")


def _seed() -> None:
    # Default tenant + builtin roles/permissions + a bootstrap admin user.
    tenants = sa.table("tenants", sa.column("id", sa.String), sa.column("name", sa.String))
    op.bulk_insert(tenants, [{"id": "default", "name": "default"}])

    permissions = sa.table("permissions", sa.column("id", sa.String), sa.column("code", sa.String))
    op.bulk_insert(
        permissions,
        [
            {"id": "p_agent_create", "code": "agent:create"},
            {"id": "p_agent_edit", "code": "agent:edit"},
            {"id": "p_agent_view", "code": "agent:view"},
            {"id": "p_agent_delete", "code": "agent:delete"},
            {"id": "p_tool_register", "code": "tool:register"},
            {"id": "p_tool_view", "code": "tool:view"},
            {"id": "p_skill_register", "code": "skill:register"},
            {"id": "p_skill_view", "code": "skill:view"},
            {"id": "p_run_execute", "code": "run:execute"},
            {"id": "p_run_view", "code": "run:view"},
            {"id": "p_run_cancel", "code": "run:cancel"},
            {"id": "p_role_manage", "code": "role:manage"},
            {"id": "p_grant_manage", "code": "grant:manage"},
            {"id": "p_user_manage", "code": "user:manage"},
        ],
    )

    roles = sa.table(
        "roles",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("is_builtin", sa.Boolean),
    )
    op.bulk_insert(
        roles,
        [
            {"id": "role_admin", "tenant_id": "default", "name": "admin", "is_builtin": True},
            {"id": "role_developer", "tenant_id": "default", "name": "developer", "is_builtin": True},
            {"id": "role_operator", "tenant_id": "default", "name": "operator", "is_builtin": True},
            {"id": "role_viewer", "tenant_id": "default", "name": "viewer", "is_builtin": True},
        ],
    )

    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_id", sa.String),
        sa.column("permission_id", sa.String),
    )
    developer_codes = [
        "p_agent_create", "p_agent_edit", "p_agent_view", "p_agent_delete",
        "p_tool_register", "p_tool_view", "p_skill_register", "p_skill_view",
        "p_run_execute", "p_run_view",
    ]
    operator_codes = ["p_run_execute", "p_run_view", "p_run_cancel"]
    viewer_codes = ["p_agent_view", "p_tool_view", "p_skill_view", "p_run_view"]
    admin_codes = [
        "p_agent_create", "p_agent_edit", "p_agent_view", "p_agent_delete",
        "p_tool_register", "p_tool_view", "p_skill_register", "p_skill_view",
        "p_run_execute", "p_run_view", "p_run_cancel",
        "p_role_manage", "p_grant_manage", "p_user_manage",
    ]
    rows = []
    for code in admin_codes:
        rows.append({"role_id": "role_admin", "permission_id": code})
    for code in developer_codes:
        rows.append({"role_id": "role_developer", "permission_id": code})
    for code in operator_codes:
        rows.append({"role_id": "role_operator", "permission_id": code})
    for code in viewer_codes:
        rows.append({"role_id": "role_viewer", "permission_id": code})
    op.bulk_insert(role_permissions, rows)

    # Bootstrap admin user. The password comes from BOOTSTRAP_ADMIN_PASSWORD so that a real
    # deployment never has its admin credential sitting in version control.
    #
    # Editing this seed after the fact is safe: it is data, not schema, and Alembic will not
    # re-run 0002 on a database that already applied it. Such databases keep whatever password
    # they were seeded with and can rotate it via POST /v1/auth/change-password.
    import os

    from smartagent.api.security import hash_password

    admin_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if not admin_password:
        admin_password = "admin123"
        print(
            "WARNING: BOOTSTRAP_ADMIN_PASSWORD is not set; seeding the admin account with the "
            "well-known default 'admin123'. Change it immediately via POST /v1/auth/change-password."
        )

    users = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("username", sa.String),
        sa.column("password_hash", sa.String),
    )
    op.bulk_insert(
        users,
        [{"id": "admin", "tenant_id": "default", "name": "Admin", "username": "admin", "password_hash": hash_password(admin_password)}],
    )

    user_roles = sa.table("user_roles", sa.column("user_id", sa.String), sa.column("role_id", sa.String))
    op.bulk_insert(user_roles, [{"user_id": "admin", "role_id": "role_admin"}])
