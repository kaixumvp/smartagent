from datetime import datetime

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    username: str
    password: str
    # Usernames are unique per tenant, not globally. Optional so single-tenant clients are
    # unaffected; required in practice once the same username exists in two tenants.
    tenant: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    # Length is the only password rule with real evidence behind it; complexity rules mostly
    # push people toward predictable substitutions.
    new_password: str = Field(min_length=8)


# --------------------------------------------------------------------------- users
class UserCreateRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    name: str = ""
    roles: list[str] = Field(default_factory=list)  # role *names* within the caller's tenant


class UserUpdateRequest(BaseModel):
    status: str | None = None  # active | disabled
    roles: list[str] | None = None  # None leaves roles alone; a list replaces the whole set


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8)


class UserOut(BaseModel):
    """Never carries `password_hash` — that field must not leave the database."""

    id: str
    tenant_id: str
    username: str
    name: str
    status: str
    roles: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


# --------------------------------------------------------------------------- runs
class RunCreateRequest(BaseModel):
    input: str
    stream: bool = False
    user_id: str | None = None


class StepOut(BaseModel):
    seq: int
    node: str
    action: str | None = None
    input: dict | None = None
    output: dict | None = None
    status: str = "success"
    latency_ms: int | None = None


class UsageOut(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class PendingApprovalOut(BaseModel):
    resource_type: str
    resource_id: str


class RunOut(BaseModel):
    run_id: str
    agent_id: str
    status: str
    result: str | None = None
    steps: list[StepOut] = Field(default_factory=list)
    usage: UsageOut = Field(default_factory=UsageOut)
    pending_approvals: list[PendingApprovalOut] = Field(default_factory=list)
    created_at: datetime | None = None
    finished_at: datetime | None = None


class RunActionRequest(BaseModel):
    action: str  # approve | reject
    resource_type: str | None = None
    resource_id: str | None = None


# --------------------------------------------------------------------------- agents
class AgentCreateRequest(BaseModel):
    name: str
    version: str = "1"
    config: dict = Field(default_factory=dict)


class AgentOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    version: str
    status: str
    config: dict
    is_latest: bool = False


# --------------------------------------------------------------------------- tools
class ToolCreateRequest(BaseModel):
    name: str
    type: str = "builtin"  # builtin | mcp | http
    description: str = ""
    endpoint: str | None = None
    config: dict | None = None
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    permission: str = "read"
    requires_approval: bool = False


class ToolOut(BaseModel):
    id: str
    name: str
    type: str
    description: str | None = None
    parameters: dict
    permission: str
    requires_approval: bool = False


# --------------------------------------------------------------------------- skills
class SkillCreateRequest(BaseModel):
    name: str
    version: str = "1"
    type: str  # prompt | function | flow | agent
    description: str = ""
    body: dict = Field(default_factory=dict)
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})
    permission: str = "read"
    requires_approval: bool = False
    tags: list[str] = Field(default_factory=list)


class SkillOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    version: str
    type: str
    description: str | None = None
    is_latest: bool = False
    status: str = "active"


# --------------------------------------------------------------------------- IAM
class RoleCreateRequest(BaseModel):
    name: str
    permission_codes: list[str] = Field(default_factory=list)


class RoleOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    is_builtin: bool = False


class RolePermissionBindRequest(BaseModel):
    permission_codes: list[str]


class GrantCreateRequest(BaseModel):
    principal_type: str  # user | role
    principal_id: str
    resource_type: str  # tool | skill | agent | knowledge
    resource_id: str
    action: str = "execute"
    effect: str = "allow"  # allow | deny


class GrantOut(BaseModel):
    id: str
    tenant_id: str
    principal_type: str
    principal_id: str
    resource_type: str
    resource_id: str
    action: str
    effect: str


# --------------------------------------------------------------------------- memory
class MemoryRecallRequest(BaseModel):
    query: str
    user_id: str | None = None
    top_k: int = 5


class MemoryEntryOut(BaseModel):
    id: str
    content: str
    similarity: float | None = None
    importance: float = 0.5
    confidence: float = 0.5


# --------------------------------------------------------------------------- evaluation (V1.1)
class GoldenCaseIn(BaseModel):
    task: str
    reference: str | None = None  # ideal answer; omit to score relevance instead of a match
    meta: dict | None = None


class GoldenCaseOut(GoldenCaseIn):
    id: str


class GoldenSetCreateRequest(BaseModel):
    name: str
    description: str = ""
    cases: list[GoldenCaseIn] = Field(default_factory=list)


class GoldenSetOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None = None
    status: str = "active"
    cases: list[GoldenCaseOut] = Field(default_factory=list)
    created_at: datetime | None = None


class EvaluationCreateRequest(BaseModel):
    golden_set_id: str
    agent_id: str
    judge_type: str = "llm"  # llm | heuristic
    judge_model: str | None = None  # defaults to settings.judge_model, then llm_model


class EvaluationResultOut(BaseModel):
    case_id: str
    run_id: str | None = None
    output: str | None = None
    score: float = 0.0
    passed: bool = False
    reason: str | None = None
    latency_ms: int | None = None
    cost: float = 0.0
    error: str | None = None


class EvaluationOut(BaseModel):
    id: str
    tenant_id: str
    golden_set_id: str
    agent_id: str
    status: str  # queued | running | completed | failed
    judge_type: str
    judge_model: str | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_score: float = 0.0
    cost: float = 0.0
    error: str | None = None
    results: list[EvaluationResultOut] = Field(default_factory=list)
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FeedbackCreateRequest(BaseModel):
    rating: int  # -1 / 1 for thumbs, or 1..5 — the scale is the caller's convention
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)


class FeedbackOut(BaseModel):
    id: str
    run_id: str
    user_id: str | None = None
    rating: int
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


# --------------------------------------------------------------------------- experiments (V1.1)
class VariantIn(BaseModel):
    label: str
    agent_id: str
    weight: float = 50.0


class ExperimentCreateRequest(BaseModel):
    name: str
    entry_agent_id: str
    variants: list[VariantIn]
    description: str = ""
    sticky_key: str = "user"


class ExperimentOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None = None
    entry_agent_id: str
    status: str  # draft | running | stopped
    variants: list[VariantIn] = Field(default_factory=list)
    sticky_key: str = "user"
    created_at: datetime | None = None


class ExperimentStatusRequest(BaseModel):
    action: str  # start | stop


class VariantStatsOut(BaseModel):
    variant: str
    agent_id: str | None = None
    runs: int = 0
    completed: int = 0
    failed: int = 0
    avg_cost: float = 0.0
    avg_latency_ms: float = 0.0
    feedback_count: int = 0
    avg_rating: float | None = None


class ExperimentResultsOut(BaseModel):
    experiment_id: str
    status: str
    variants: list[VariantStatsOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- cost (V1.1)
class CostBucketOut(BaseModel):
    key: str
    runs: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0


class CostSummaryOut(BaseModel):
    group_by: str  # agent | model | experiment
    total_cost: float = 0.0
    total_runs: int = 0
    buckets: list[CostBucketOut] = Field(default_factory=list)


class CacheStatsOut(BaseModel):
    enabled: bool
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    size: int = 0


# --------------------------------------------------------------------------- errors
class ErrorDetail(BaseModel):
    code: str
    message: str
    trace_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
