"""V1.1: evaluation closed loop, A/B experiments, cost accounting.

Adds the three V1.1 business pillars:
- evaluation: golden sets/cases, async evaluation jobs and per-case results, online feedback
- experiments: agent version grouping (`agents.is_latest`) + weighted sticky traffic split
- cost: per-run model and cost attribution (`runs.cost` has existed since 0001 but was never
  written; V1.1 is where it starts carrying real numbers)

Two deliberate choices worth knowing:
- `agents` gets a NON-unique (tenant_id, name, version) index plus a PARTIAL UNIQUE index on
  (tenant_id, name) WHERE is_latest. A plain unique on (tenant, name, version) would require
  mutating pre-existing duplicate rows, which this migration refuses to do. The invariant A/B
  actually depends on — at most one latest per logical agent — is still hard-enforced.
- Unlike 0002, the permission seeding here is idempotent (ON CONFLICT DO NOTHING, role ids
  resolved by name) so a partial run or a shared database does not wedge the migration.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-26

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_PERMISSIONS = [
    ("p_eval_manage", "eval:manage", "Create golden sets and launch evaluations"),
    ("p_eval_view", "eval:view", "View evaluations and results"),
    ("p_experiment_manage", "experiment:manage", "Create and start/stop A/B experiments"),
    ("p_experiment_view", "experiment:view", "View experiments and their results"),
]

# role name -> permission codes granted
_ROLE_GRANTS = {
    "admin": ["eval:manage", "eval:view", "experiment:manage", "experiment:view"],
    "developer": ["eval:manage", "eval:view", "experiment:view"],
    "operator": ["eval:view", "experiment:view"],
    "viewer": ["eval:view", "experiment:view"],
}


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, postgresql.TIMESTAMP(timezone=True), **kw)


def upgrade() -> None:
    # ----------------------------------------------------------------- evaluation
    op.create_table(
        "golden_sets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("owner", sa.String(64)),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("updated_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_golden_sets_tenant_name", "golden_sets", ["tenant_id", "name"], unique=True)

    op.create_table(
        "golden_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("golden_set_id", sa.String(64), sa.ForeignKey("golden_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text()),
        sa.Column("meta", postgresql.JSONB()),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_golden_cases_set", "golden_cases", ["golden_set_id"])

    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("golden_set_id", sa.String(64), sa.ForeignKey("golden_sets.id"), nullable=False),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        # queued | running | completed | failed | canceled
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("judge_type", sa.String(16), nullable=False, server_default="llm"),  # llm | heuristic
        sa.Column("judge_model", sa.String(64)),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Numeric(6, 4, asdecimal=False), nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 6, asdecimal=False), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("created_by", sa.String(64)),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("started_at"),
        _ts("finished_at"),
    )
    op.create_index("idx_evaluations_tenant_time", "evaluations", ["tenant_id", "created_at"])
    op.create_index("idx_evaluations_agent", "evaluations", ["agent_id"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("evaluation_id", sa.String(64), sa.ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64)),
        sa.Column("output", sa.Text()),
        sa.Column("score", sa.Numeric(6, 4, asdecimal=False), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reason", sa.Text()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("token_usage", postgresql.JSONB()),
        sa.Column("cost", sa.Numeric(12, 6, asdecimal=False), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_eval_results_eval", "evaluation_results", ["evaluation_id"])

    op.create_table(
        "feedbacks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(64)),
        sa.Column("rating", sa.Integer(), nullable=False),  # -1 | 1, or 1..5
        sa.Column("comment", sa.Text()),
        sa.Column("tags", postgresql.JSONB()),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_feedbacks_run", "feedbacks", ["run_id"])
    op.create_index("idx_feedbacks_tenant_time", "feedbacks", ["tenant_id", "created_at"])

    # ----------------------------------------------------------------- experiments
    op.create_table(
        "agent_experiments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
        # The agent clients actually call; traffic to it is split across `variants`.
        sa.Column("entry_agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),  # draft|running|stopped
        # [{"label": "A", "agent_id": "agent_...", "weight": 50}, ...] — frozen once running:
        # moving weights would shift bucket boundaries and silently re-bucket assigned users.
        sa.Column("variants", postgresql.JSONB(), nullable=False),
        sa.Column("sticky_key", sa.String(16), nullable=False, server_default="user"),  # user | run
        sa.Column("created_by", sa.String(64)),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
        _ts("started_at"),
        _ts("stopped_at"),
    )
    op.create_index("uq_experiments_tenant_name", "agent_experiments", ["tenant_id", "name"], unique=True)
    op.create_index("idx_experiments_entry", "agent_experiments", ["entry_agent_id", "status"])

    op.create_table(
        "experiment_assignments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("experiment_id", sa.String(64), sa.ForeignKey("agent_experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_key", sa.String(128), nullable=False),
        sa.Column("variant", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        _ts("created_at", nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_exp_assignments", "experiment_assignments", ["experiment_id", "subject_key"], unique=True
    )

    # ----------------------------------------------------------------- agent versioning
    op.add_column("agents", sa.Column("is_latest", sa.Boolean(), nullable=False, server_default="false"))
    # Deterministic backfill: one winner per (tenant_id, name). `created_at`/`updated_at` both
    # default to now(), so rows inserted in one batch tie — `id` breaks it. Never order by
    # `version`: it is a free-form string where "9" sorts above "10".
    op.execute(
        """
        UPDATE agents SET is_latest = true
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY tenant_id, name
                    ORDER BY created_at DESC, updated_at DESC, id ASC
                ) AS rn
                FROM agents
            ) ranked
            WHERE ranked.rn = 1
        )
        """
    )
    op.create_index("idx_agents_tenant_name_ver", "agents", ["tenant_id", "name", "version"])
    op.create_index(
        "uq_agents_tenant_name_latest",
        "agents",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_latest"),
    )

    # ----------------------------------------------------------------- run attribution
    op.add_column("runs", sa.Column("model", sa.String(64)))
    op.add_column("runs", sa.Column("experiment_id", sa.String(64)))
    op.add_column("runs", sa.Column("variant", sa.String(64)))
    # Lets the restart sweep scope itself to evaluation-owned runs, instead of blanket-failing
    # every `awaiting_human` run (which would kill legitimate interactive HITL runs).
    op.add_column("runs", sa.Column("evaluation_id", sa.String(64)))
    op.create_index("idx_runs_experiment", "runs", ["experiment_id"])
    op.create_index("idx_runs_evaluation", "runs", ["evaluation_id"])

    # ----------------------------------------------------------------- permissions (idempotent)
    values = ", ".join(f"('{pid}', '{code}', '{desc}')" for pid, code, desc in _NEW_PERMISSIONS)
    op.execute(
        f"INSERT INTO permissions (id, code, description) VALUES {values} ON CONFLICT DO NOTHING"
    )
    for role_name, codes in _ROLE_GRANTS.items():
        code_list = ", ".join(f"'{c}'" for c in codes)
        op.execute(
            f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
            WHERE r.name = '{role_name}' AND p.code IN ({code_list})
            ON CONFLICT DO NOTHING
            """
        )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for _, code, _ in _NEW_PERMISSIONS)
    # role_permissions.permission_id cascades on delete, so the bindings go with the rows.
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")

    op.drop_index("idx_runs_evaluation", table_name="runs")
    op.drop_index("idx_runs_experiment", table_name="runs")
    op.drop_column("runs", "evaluation_id")
    op.drop_column("runs", "variant")
    op.drop_column("runs", "experiment_id")
    op.drop_column("runs", "model")

    op.drop_index("uq_agents_tenant_name_latest", table_name="agents")
    op.drop_index("idx_agents_tenant_name_ver", table_name="agents")
    op.drop_column("agents", "is_latest")

    op.drop_table("experiment_assignments")
    op.drop_table("agent_experiments")
    op.drop_table("feedbacks")
    op.drop_table("evaluation_results")
    op.drop_table("evaluations")
    op.drop_table("golden_cases")
    op.drop_table("golden_sets")
