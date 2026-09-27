from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# Embedding dimension for the Vector Memory index. Must match settings.embedding_dimension;
# changing it after table creation requires rebuilding the vector index.
VECTOR_DIM = 1536


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    quota: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_tenant_username", "tenant_id", "username", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (Index("uq_roles_tenant_name", "tenant_id", "name", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(64), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(String(64), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(String(64), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        Index("idx_grants_principal", "tenant_id", "principal_type", "principal_id"),
        Index("idx_grants_resource", "tenant_id", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)  # user | role
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(16), nullable=False)  # tool | skill | agent | knowledge
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # execute | read | write | admin
    effect: Mapped[str] = mapped_column(String(8), nullable=False, default="allow", server_default="allow")  # allow | deny
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Tool(Base):
    __tablename__ = "tools"
    __table_args__ = (Index("idx_tools_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", server_default="default")
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="builtin", server_default="builtin")
    description: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    permission: Mapped[str] = mapped_column(String(16), nullable=False, default="read", server_default="read")
    endpoint: Mapped[str | None] = mapped_column(Text)  # MCP server URL / OpenAPI spec URL
    config: Mapped[dict | None] = mapped_column(JSONB)  # auth / headers / timeouts / tool filters
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    owner: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("idx_agents_tenant", "tenant_id"),
        Index("idx_agents_tenant_name_ver", "tenant_id", "name", "version"),
        # At most one latest version per logical agent — the invariant A/B routing relies on.
        # Deliberately NOT a unique (tenant, name, version): that would require mutating
        # pre-existing duplicate rows (see Alembic 0004).
        Index("uq_agents_tenant_name_latest", "tenant_id", "name", unique=True, postgresql_where="is_latest"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", server_default="default")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1", server_default="1")
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    tools: Mapped[list["Tool"]] = relationship(secondary="agent_tools", lazy="selectin")


class AgentTool(Base):
    __tablename__ = "agent_tools"

    agent_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    tool_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True
    )


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        Index("uq_skills_tenant_name_ver", "tenant_id", "name", "version", unique=True),
        Index("idx_skills_latest", "tenant_id", "name", postgresql_where="is_latest"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # prompt | function | flow | agent
    description: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    owner: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("idx_runs_agent", "agent_id", "created_at"),
        Index("idx_runs_tenant", "tenant_id", "created_at"),
        Index("idx_runs_parent", "parent_run_id"),
        Index("idx_runs_experiment", "experiment_id"),
        Index("idx_runs_evaluation", "evaluation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default", server_default="default")
    user_id: Mapped[str | None] = mapped_column(String(64))
    input: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    cost: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0, server_default="0")
    # V1.1 attribution: which model actually served the run (tiered routing picks per run),
    # which A/B variant it belongs to, and whether it was produced by an evaluation job.
    model: Mapped[str | None] = mapped_column(String(64))
    experiment_id: Mapped[str | None] = mapped_column(String(64))
    variant: Mapped[str | None] = mapped_column(String(64))
    evaluation_id: Mapped[str | None] = mapped_column(String(64))
    approvals: Mapped[list | None] = mapped_column(JSONB)  # high-risk resources approved within this run
    # Framework run-state snapshot (ouroboros Checkpointer port); cleared on terminal status.
    checkpoint: Mapped[dict | None] = mapped_column(JSONB)
    # Resources the run is currently blocked on, echoed by GET /runs/{id}.
    pending_approvals: Mapped[list | None] = mapped_column(JSONB)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runs.id"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (Index("idx_run_steps_run", "run_id", "seq"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str | None] = mapped_column(String(128))
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class VectorMemory(Base):
    __tablename__ = "vector_memories"
    __table_args__ = (Index("idx_vecmem_tenant_user", "tenant_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(VECTOR_DIM), nullable=False)
    importance: Mapped[float] = mapped_column(Numeric(6, 3, asdecimal=False), nullable=False, default=0.5, server_default="0.5")
    confidence: Mapped[float] = mapped_column(Numeric(6, 3, asdecimal=False), nullable=False, default=0.5, server_default="0.5")
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_access: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ttl: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# --------------------------------------------------------------------------- V1.1 evaluation
class GoldenSet(Base):
    """A named regression suite: the cases an agent must keep passing across versions."""

    __tablename__ = "golden_sets"
    __table_args__ = (Index("uq_golden_sets_tenant_name", "tenant_id", "name", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    owner: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    cases: Mapped[list["GoldenCase"]] = relationship(
        back_populates="golden_set", lazy="selectin", cascade="all, delete-orphan"
    )


class GoldenCase(Base):
    __tablename__ = "golden_cases"
    __table_args__ = (Index("idx_golden_cases_set", "golden_set_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    golden_set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("golden_sets.id", ondelete="CASCADE"), nullable=False
    )
    task: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)  # ideal answer the judge compares against
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    golden_set: Mapped["GoldenSet"] = relationship(back_populates="cases")


class Evaluation(Base):
    """One asynchronous evaluation job: a golden set run against one agent."""

    __tablename__ = "evaluations"
    __table_args__ = (
        Index("idx_evaluations_tenant_time", "tenant_id", "created_at"),
        Index("idx_evaluations_agent", "agent_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    golden_set_id: Mapped[str] = mapped_column(String(64), ForeignKey("golden_sets.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", server_default="queued")
    judge_type: Mapped[str] = mapped_column(String(16), nullable=False, default="llm", server_default="llm")
    judge_model: Mapped[str | None] = mapped_column(String(64))
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    avg_score: Mapped[float] = mapped_column(Numeric(6, 4, asdecimal=False), nullable=False, default=0, server_default="0")
    cost: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (Index("idx_eval_results_eval", "evaluation_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64))
    output: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Numeric(6, 4, asdecimal=False), nullable=False, default=0, server_default="0")
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reason: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    cost: Mapped[float] = mapped_column(Numeric(12, 6, asdecimal=False), nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Feedback(Base):
    """Online user feedback on a completed run — the other half of the evaluation signal."""

    __tablename__ = "feedbacks"
    __table_args__ = (
        Index("idx_feedbacks_run", "run_id"),
        Index("idx_feedbacks_tenant_time", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# --------------------------------------------------------------------------- V1.1 experiments
class AgentExperiment(Base):
    """A/B experiment: traffic to `entry_agent_id` is split across `variants`."""

    __tablename__ = "agent_experiments"
    __table_args__ = (
        Index("uq_experiments_tenant_name", "tenant_id", "name", unique=True),
        Index("idx_experiments_entry", "entry_agent_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entry_agent_id: Mapped[str] = mapped_column(String(64), ForeignKey("agents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    # [{"label": "A", "agent_id": "...", "weight": 50}, ...]
    # Frozen once running: shifting weights moves bucket boundaries and silently re-buckets
    # already-assigned subjects. Change the split by creating a new experiment.
    variants: Mapped[list] = mapped_column(JSONB, nullable=False)
    sticky_key: Mapped[str] = mapped_column(String(16), nullable=False, default="user", server_default="user")
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ExperimentAssignment(Base):
    """Persisted variant assignment, so a subject's bucket is auditable, not just recomputable."""

    __tablename__ = "experiment_assignments"
    __table_args__ = (Index("uq_exp_assignments", "experiment_id", "subject_key", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agent_experiments.id", ondelete="CASCADE"), nullable=False
    )
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    variant: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_tenant_time", "tenant_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    actor: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(16))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # allow | deny | approve | reject
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
