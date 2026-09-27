"""Cross-layer ports shared by the agent framework and its host (business layer).

The framework depends ONLY on these protocols/types (plus its own modules); the business
layer implements them. This keeps the framework free of any import of the host's storage,
HTTP, or configuration.

V0.3 consolidates *all* framework↔host contracts here so that ``import src.ports``
is the single place to read the ABI. Concrete implementations (LiteLLM gateway/embedder,
Redis working memory, …) stay in their own modules and re-export the protocol for
backward compatibility.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- LLM
class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: dict = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


class LLMGateway(Protocol):
    """The LLM backend. A host may supply LiteLLM, a mock, or a multi-vendor router."""

    async def chat(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------- embedder
class Embedder(Protocol):
    """Text → vector, used by long-term memory for semantic recall."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


# --------------------------------------------------------------------------- plugin
def _default_json_schema() -> dict:
    return {"type": "object", "properties": {}, "required": []}


class PluginManifest(BaseModel):
    """Declarative metadata for a plugin: what it is, its parameters, and its required permission."""

    name: str
    version: str = "1"
    kind: str  # tool | skill | knowledge | model | memory | node
    description: str = ""
    parameters: dict = Field(default_factory=_default_json_schema)
    permission: str = "read"  # read | write | admin
    requires_approval: bool = False
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def function_name(self) -> str:
        """OpenAI function-calling name. Tools keep their bare name; other kinds are
        namespaced so they never collide with a tool of the same name."""
        return self.name if self.kind == "tool" else f"{self.kind}_{self.name}"


class InvokeContext(BaseModel):
    """Cross-cutting context handed to every plugin invocation."""

    tenant_id: str = "default"
    user_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    session_id: str | None = None
    subagent_depth: int = 0


class Plugin(Protocol):
    """Unified plugin protocol. Tool/Skill/Knowledge/etc. all implement this."""

    kind: str
    manifest: PluginManifest

    async def setup(self, config: dict) -> None: ...
    async def invoke(self, ctx: InvokeContext, **kw: Any) -> Any: ...
    async def teardown(self) -> None: ...


# --------------------------------------------------------------------------- permission
class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class Principal(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str] = Field(default_factory=list)
    is_admin: bool = False


class PermissionContext(BaseModel):
    permission_codes: set[str] = Field(default_factory=set)
    grant_keys: set[tuple[str, str, str]] = Field(default_factory=set)  # (resource_type, resource_id, effect)
    is_admin: bool = False


def check_permission(
    ctx: PermissionContext,
    action: str,
    resource_type: str,
    resource_id: str,
    resource_permission: str = "read",
    requires_approval: bool = False,
    approved: set[str] | None = None,
) -> PermissionDecision:
    """Pure authorization decision over a pre-loaded context (spec §10.3)."""
    if ctx.is_admin:
        return PermissionDecision.ALLOW
    if action == "execute" and "run:execute" not in ctx.permission_codes:
        return PermissionDecision.DENY
    if (resource_type, resource_id, "deny") in ctx.grant_keys:
        return PermissionDecision.DENY
    if resource_permission == "read" and not requires_approval:
        return PermissionDecision.ALLOW
    if (resource_type, resource_id, "allow") not in ctx.grant_keys:
        return PermissionDecision.DENY
    if resource_permission == "admin" or requires_approval:
        approved = approved or set()
        if resource_id not in approved:
            return PermissionDecision.REQUIRE_APPROVAL
    return PermissionDecision.ALLOW


class PermissionChecker(Protocol):
    def check(
        self,
        ctx: PermissionContext,
        action: str,
        resource_type: str,
        resource_id: str,
        resource_permission: str = "read",
        requires_approval: bool = False,
        approved: set[str] | None = None,
    ) -> PermissionDecision: ...


# --------------------------------------------------------------------------- memory
class MemoryEntry(BaseModel):
    id: str
    tenant_id: str
    user_id: str | None = None
    session_id: str | None = None
    content: str
    importance: float = 0.5
    confidence: float = 0.5
    source: str = "vector"
    similarity: float | None = None
    created_at: datetime | None = None


class WorkingMemory(Protocol):
    async def get_history(self, session_id: str) -> list[dict]: ...
    async def append(self, session_id: str, message: dict) -> None: ...


class LongTermMemory(Protocol):
    async def add(
        self,
        db: Any,
        *,
        tenant_id: str,
        user_id: str | None,
        session_id: str | None,
        content: str,
        importance: float = 0.5,
        confidence: float = 0.5,
    ) -> str: ...

    async def recall(
        self,
        db: Any,
        tenant_id: str,
        user_id: str | None,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryEntry]: ...


# --------------------------------------------------------------------------- knowledge
class KnowledgeEntry(BaseModel):
    """A single retrieved knowledge document."""

    id: str
    content: str
    source: str | None = None
    metadata: dict = Field(default_factory=dict)
    similarity: float | None = None


class Retriever(Protocol):
    """Low-level retrieval primitive (embedding + top-k over an index)."""

    async def retrieve(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]: ...


class Knowledge(Protocol):
    """Higher-level knowledge port: search + ingest (the host owns the RAG pipeline)."""

    async def search(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]: ...
    async def add(
        self,
        *,
        content: str,
        source: str | None = None,
        metadata: dict | None = None,
    ) -> str: ...


# --------------------------------------------------------------------------- events
class EventSink(Protocol):
    """Sink for runtime events. The event is a ``ouroboros.events.events.RuntimeEvent``;
    typed as Any here to avoid a ports↔events import cycle."""

    async def __call__(self, event: Any) -> None: ...


# --------------------------------------------------------------------------- subgraph runners
SubagentRunner = Callable[[str, str, InvokeContext], Awaitable[str]]  # (agent_ref, task, ctx)
FlowRunner = Callable[[dict, InvokeContext, dict], Awaitable[str]]  # (graph_spec, ctx, kw)


# --------------------------------------------------------------------------- evaluation
class JudgeVerdict(BaseModel):
    """A judge's verdict on a single output."""

    score: float = 0.0  # 0..1
    passed: bool = False
    reason: str = ""


class Judge(Protocol):
    """LLM-as-judge (or heuristic) for offline evaluation. Implemented by the host."""

    async def judge(self, *, task: str, output: str, reference: str | None = None) -> JudgeVerdict: ...


# --------------------------------------------------------------------------- metrics
class Metrics(Protocol):
    """Observability metrics sink (V0.4). Hosts implement to push to Prometheus etc."""

    def incr(self, name: str, value: int = 1, labels: dict[str, str] | None = None) -> None: ...
    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None: ...


# --------------------------------------------------------------------------- checkpointer
class Checkpointer(Protocol):
    """Persists a run's state so it can be resumed (pause/human-in-the-loop or crash recovery).

    The framework supplies the state dict; where it is stored is the host's concern
    (Redis, Postgres, S3, …). ``ouroboros.core.checkpointer.InMemoryCheckpointer`` is the
    zero-dependency default used in tests.
    """

    async def save(self, run_id: str, state: dict) -> None: ...
    async def load(self, run_id: str) -> dict | None: ...
    async def delete(self, run_id: str) -> None: ...
