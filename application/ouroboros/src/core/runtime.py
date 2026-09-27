"""AgentRuntime facade (V0.3): the strongly-typed entry point for driving a run.

Replaces the V0.1/V0.2 ``build_graph`` + ``run_agent`` dict-based loop with a typed
``run(definition, task, context, deps) -> RunResult``, and adds the reliability features the
old loop lacked: retry + circuit breaker, a hard timeout, sub-agent depth enforcement,
checkpointed pause/resume (human-in-the-loop), and an ``EventSink`` callback.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from src.core.nodes import decide as decide_mod
from src.core.nodes import execute as execute_mod
from src.core.nodes import observe as observe_mod
from src.core.nodes import plan as plan_mod
from src.core.resilience import CircuitBreaker, CircuitOpenError, RetryPolicy, run_with_retry
from src.events.events import (
    run_approved,
    run_awaiting_human,
    run_completed,
    run_failed,
    run_started,
    step_completed,
)
from src.llm.cost import TokenBudgetExceeded
from src.observability.metrics import noop_metrics
from src.observability.trace import default_tracer
from src.plugins.registry import PluginRegistry
from src.ports import (
    Checkpointer,
    Embedder,
    EventSink,
    FlowRunner,
    Knowledge,
    LLMGateway,
    LongTermMemory,
    Metrics,
    PermissionChecker,
    PermissionContext,
    SubagentRunner,
    WorkingMemory,
)
from src.security import Redactor, default_redactor

logger = logging.getLogger(__name__)

# Internal state key recording the next node to run; persists in checkpoints so a resume
# knows exactly where to continue (e.g. re-run `execute` after an approval).
_NEXT = "_next_node"


# --------------------------------------------------------------------------- data types
class RuntimeConfig(BaseModel):
    max_iterations: int = 20
    timeout_seconds: float = 120.0
    max_subagent_depth: int = 3
    max_total_tokens: int = 0  # 0 = unlimited token budget (V1.1)


class Step(BaseModel):
    seq: int
    node: str
    action: str | None = None
    output: dict | None = None
    status: str = "success"
    latency_ms: int | None = None
    run_id: str | None = None


class RunResult(BaseModel):
    status: str  # completed | failed | awaiting_human | canceled
    result: str | None = None
    error: str | None = None
    steps: list[Step] = Field(default_factory=list)
    token_usage: dict = Field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    pending_approvals: list[dict] = Field(default_factory=list)


class AgentDefinition(BaseModel):
    model: str
    system_prompt: str | None = None
    plugins: list[Any] = Field(default_factory=list)  # list[Plugin] — pydantic can't validate protocols
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    agent_id: str = ""


class RunContext(BaseModel):
    tenant_id: str = "default"
    user_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    subagent_depth: int = 0


@dataclass
class RuntimeDeps:
    """Port implementations injected by the host. Only `llm` is required."""

    llm: LLMGateway
    embedder: Embedder | None = None
    permission_checker: PermissionChecker | None = None
    permission_context: PermissionContext | None = None
    working_memory: WorkingMemory | None = None
    long_term_memory: LongTermMemory | None = None
    knowledge: Knowledge | None = None
    event_sink: EventSink | None = None
    subagent_runner: SubagentRunner | None = None
    flow_runner: FlowRunner | None = None
    checkpointer: Checkpointer | None = None
    db: Any = None  # transparent handle passed through to LongTermMemory/Knowledge ports
    id_gen: Callable[[str], str] | None = None
    retry: RetryPolicy | None = None
    circuit_breaker: CircuitBreaker | None = None
    tracer: Any = None  # ouroboros.observability.Tracer; None → module default
    metrics: Metrics | None = None  # None → no-op
    redactor: Redactor | None = None  # None → module default (built-in patterns)


# --------------------------------------------------------------------------- runtime
class AgentRuntime:
    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self._config = config or RuntimeConfig()

    async def run(
        self,
        definition: AgentDefinition,
        task: str,
        context: RunContext,
        deps: RuntimeDeps,
        *,
        history: list[dict] = (),
        memory_context: list[dict] = (),
        approvals: list[str] = (),
    ) -> RunResult:
        cfg = definition.runtime or self._config
        run_id = context.run_id or self._gen_id(deps, "run")
        tracer = deps.tracer or default_tracer
        recalled = await self._recall_context(deps, context, task)
        state = self._initial_state(
            definition, task, context, run_id, cfg, history, list(memory_context) + recalled, approvals
        )
        registry = self._build_registry(definition)
        await self._emit(deps, run_started(run_id))
        with tracer.start_span("ouroboros.run", attributes={"run_id": run_id, "agent_id": definition.agent_id}) as span:
            state["trace_id"] = tracer.current_trace_id() or self._gen_id(deps, "trace")
            try:
                return await self._drive(state, definition, deps, registry, cfg)
            except Exception as exc:  # noqa: BLE001 — safety net; _drive normally handles errors
                tracer.record_error(span, exc)
                raise

    async def resume(
        self,
        definition: AgentDefinition,
        run_id: str,
        approvals: list[str],
        deps: RuntimeDeps,
    ) -> RunResult:
        """Continue a paused run after the host grants the pending approvals.

        Requires ``deps.checkpointer``; the checkpoint holds the pre-execute state so that
        the exact blocked ``execute`` step is re-run with the newly-approved resources.
        """
        if deps.checkpointer is None:
            raise RuntimeError("resume requires a checkpointer in RuntimeDeps")
        state = await deps.checkpointer.load(run_id)
        if state is None:
            raise RuntimeError(f"no checkpoint for run_id={run_id}")
        cfg = definition.runtime or self._config
        state["approvals"] = list(state.get("approvals") or []) + list(approvals)
        state["status"] = "running"
        registry = self._build_registry(definition)
        await self._emit(deps, run_approved(run_id))
        return await self._drive(state, definition, deps, registry, cfg)

    # ------------------------------------------------------------------ internals
    def _build_registry(self, definition: AgentDefinition) -> PluginRegistry:
        registry = PluginRegistry()
        for plugin in definition.plugins:
            registry.register(plugin)
        return registry

    def _initial_state(
        self,
        definition: AgentDefinition,
        task: str,
        context: RunContext,
        run_id: str,
        cfg: RuntimeConfig,
        history: list[dict],
        memory_context: list[dict],
        approvals: list[str],
    ) -> dict:
        messages = list(history) if history else [{"role": "user", "content": task}]
        state: dict = {
            "agent_id": definition.agent_id,
            "run_id": run_id,
            "session_id": context.session_id or "",
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "task": task,
            "messages": messages,
            "plan": [],
            "action": None,
            "action_input": None,
            "tool_call_id": None,
            "tool_calls": [],
            "tool_call_ids": [],
            "tool_results": [],
            "last_tool_result": None,
            "iteration": 0,
            "max_iterations": cfg.max_iterations,
            "max_subagent_depth": cfg.max_subagent_depth,
            "status": "running",
            "result": None,
            "error": None,
            "plugins": [{"type": p.manifest.kind, "name": p.manifest.name} for p in definition.plugins],
            "memory_ctx": list(memory_context),
            "approvals": list(approvals),
            "pending_approvals": [],
            "subagent_depth": context.subagent_depth,
            "trace_id": None,
            "system_prompt": definition.system_prompt,
            "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            _NEXT: "plan",
        }
        return state

    async def _drive(
        self,
        state: dict,
        definition: AgentDefinition,
        deps: RuntimeDeps,
        registry: PluginRegistry,
        cfg: RuntimeConfig,
    ) -> RunResult:
        run_id = state.get("run_id")
        model = definition.model
        system_prompt = definition.system_prompt
        tool_schemas = registry.to_openai_schema()
        policy = deps.retry or RetryPolicy()
        tracer = deps.tracer or default_tracer
        metrics = deps.metrics or noop_metrics
        redactor = deps.redactor or default_redactor
        steps: list[Step] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        seq = 0
        run_started_at = time.perf_counter()

        try:
            async with asyncio.timeout(cfg.timeout_seconds or None):
                while True:
                    node = state.get(_NEXT)
                    if node is None:
                        break
                    seq += 1
                    update, latency_ms = await self._run_node(
                        node, state, model, system_prompt, tool_schemas, registry, deps, policy, tracer, metrics
                    )
                    state.update(update)
                    self._merge_usage(usage, update)
                    if cfg.max_total_tokens and usage["total_tokens"] > cfg.max_total_tokens:
                        raise TokenBudgetExceeded(
                            f"token budget exceeded: {usage['total_tokens']} > {cfg.max_total_tokens}"
                        )

                    step = Step(
                        seq=seq,
                        node=node,
                        action=update.get("action"),
                        output=redactor.redact(self._step_output(node, update)),
                        status="awaiting_human" if update.get("status") == "awaiting_human" else "success",
                        latency_ms=latency_ms,
                        run_id=run_id,
                    )
                    steps.append(step)
                    await self._emit(deps, step_completed(step))

                    state[_NEXT] = self._next(node, state)
                    if node == "execute" and state.get("status") == "awaiting_human":
                        # Pause: do NOT checkpoint the post-execute state. The last saved
                        # snapshot (post-decide) is what a resume re-runs from.
                        pending = state.get("pending_approvals") or []
                        await self._emit(deps, run_awaiting_human(run_id, pending))
                        return RunResult(
                            status="awaiting_human",
                            steps=steps,
                            token_usage=usage,
                            pending_approvals=pending,
                        )
                    await self._checkpoint(deps, run_id, state)

            result = state.get("result")
            await self._emit(deps, run_completed(run_id, result, usage))
            await self._forget_checkpoint(deps, run_id)
            self._record_run(metrics, "completed", state, run_started_at, usage)
            return RunResult(status="completed", result=result, steps=steps, token_usage=usage)

        except asyncio.TimeoutError:
            error = f"run timed out after {cfg.timeout_seconds}s"
        except CircuitOpenError as exc:
            error = str(exc)
        except TokenBudgetExceeded as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("run failed: run_id=%s", run_id)
            error = str(exc)

        await self._emit(deps, run_failed(run_id, error))
        await self._forget_checkpoint(deps, run_id)
        self._record_run(metrics, "failed", state, run_started_at, usage)
        return RunResult(status="failed", error=error, steps=steps, token_usage=usage)

    async def _run_node(
        self,
        node: str,
        state: dict,
        model: str,
        system_prompt: str | None,
        tool_schemas: list[dict],
        registry: PluginRegistry,
        deps: RuntimeDeps,
        policy: RetryPolicy,
        tracer,
        metrics,
    ) -> tuple[dict, int]:
        run_id = state.get("run_id")
        start = time.perf_counter()
        with tracer.start_span(f"ouroboros.{node}", attributes={"node": node, "run_id": run_id}) as span:
            try:
                update = await run_with_retry(
                    lambda: self._call_node(
                        node, state, model, system_prompt, tool_schemas, registry, deps, tracer, metrics
                    ),
                    policy=policy,
                    breaker=deps.circuit_breaker,
                )
            except Exception as exc:  # noqa: BLE001 — mark span, then let retry/run handle it
                tracer.record_error(span, exc)
                raise
        latency_ms = int((time.perf_counter() - start) * 1000)
        metrics.observe("ouroboros.step.latency_ms", latency_ms, {"node": node})
        return update, latency_ms

    async def _call_node(
        self,
        node: str,
        state: dict,
        model: str,
        system_prompt: str | None,
        tool_schemas: list[dict],
        registry: PluginRegistry,
        deps: RuntimeDeps,
        tracer=None,
        metrics=None,
    ) -> dict:
        if node == "plan":
            return await plan_mod.run_plan(state, deps.llm, model)
        if node == "decide":
            return await decide_mod.run_decide(state, deps.llm, model, tool_schemas, system_prompt)
        if node == "execute":
            return await execute_mod.run_execute(
                state, registry, deps.permission_checker, deps.permission_context,
                tracer=tracer, metrics=metrics,
            )
        if node == "observe":
            return await observe_mod.run_observe(state)
        raise ValueError(f"unknown node: {node}")

    def _next(self, node: str, state: dict) -> str | None:
        if node == "plan":
            return "decide"
        if node == "decide":
            return None if state.get("action") == "__finish__" else "execute"
        if node == "execute":
            return None if state.get("status") == "awaiting_human" else "observe"
        if node == "observe":
            done = state.get("status") == "completed" or state.get("iteration", 0) >= state.get(
                "max_iterations", 20
            )
            return None if done else "decide"
        return None

    async def _recall_context(self, deps: RuntimeDeps, context: RunContext, task: str) -> list[dict]:
        """Recall long-term memory; when it is insufficient, fall back to the Knowledge port."""
        contexts: list[dict] = []
        entries: list[Any] = []
        if deps.long_term_memory is not None:
            try:
                entries = await deps.long_term_memory.recall(
                    deps.db, context.tenant_id, context.user_id, task, top_k=5
                )
                contexts = [{"content": e.content, "source": getattr(e, "source", "memory")} for e in entries]
            except Exception:  # noqa: BLE001 — memory is best-effort
                logger.warning("long-term memory recall failed", exc_info=True)

        sufficient = any(
            (e.similarity or 0.0) >= 0.5 or (e.confidence or 0.0) >= 0.5 for e in entries
        )
        if not sufficient and deps.knowledge is not None:
            try:
                docs = await deps.knowledge.search(task, top_k=5)
                contexts = [{"content": d.content, "source": d.source or "knowledge"} for d in docs]
                # Write the fallback back into long-term memory so the next recall is sufficient.
                if deps.long_term_memory is not None:
                    for d in docs:
                        try:
                            await deps.long_term_memory.add(
                                deps.db,
                                tenant_id=context.tenant_id,
                                user_id=context.user_id,
                                session_id=context.session_id,
                                content=d.content,
                                importance=0.3,
                                confidence=0.5,
                            )
                        except Exception:  # noqa: BLE001 — write-back is best-effort
                            pass
            except Exception:  # noqa: BLE001
                logger.warning("knowledge fallback failed", exc_info=True)

        return contexts

    def _merge_usage(self, usage: dict, update: dict) -> None:
        u = update.get("token_usage")
        if isinstance(u, dict):
            for k in usage:
                usage[k] += u.get(k, 0)

    def _step_output(self, node: str, update: dict) -> dict | None:
        if node == "plan":
            return {"plan": [s.get("description") for s in update.get("plan", [])]}
        if node == "decide":
            return {
                "action": update.get("action"),
                "action_input": update.get("action_input"),
                "result": update.get("result"),
            }
        if node == "execute":
            return {"result": update.get("last_tool_result")}
        if node == "observe":
            return {"result": update.get("result"), "iteration": update.get("iteration")}
        return None

    async def _emit(self, deps: RuntimeDeps, event: Any) -> None:
        if deps.event_sink is not None:
            redactor = deps.redactor or default_redactor
            event.data = redactor.redact(event.data)
            await deps.event_sink(event)

    def _record_run(self, metrics, status: str, state: dict, started_at: float, usage: dict) -> None:
        metrics.incr("ouroboros.runs", labels={"status": status})
        metrics.observe(
            "ouroboros.run.latency_ms", int((time.perf_counter() - started_at) * 1000), {"status": status}
        )
        metrics.incr("ouroboros.iterations", state.get("iteration", 0))
        metrics.incr("ouroboros.tokens", usage.get("total_tokens", 0), {"kind": "total"})
        metrics.incr("ouroboros.tokens", usage.get("prompt_tokens", 0), {"kind": "prompt"})
        metrics.incr("ouroboros.tokens", usage.get("completion_tokens", 0), {"kind": "completion"})

    async def _checkpoint(self, deps: RuntimeDeps, run_id: str, state: dict) -> None:
        if deps.checkpointer is not None:
            await deps.checkpointer.save(run_id, state)

    async def _forget_checkpoint(self, deps: RuntimeDeps, run_id: str) -> None:
        if deps.checkpointer is not None:
            await deps.checkpointer.delete(run_id)

    def _gen_id(self, deps: RuntimeDeps, prefix: str) -> str:
        if deps.id_gen is not None:
            return deps.id_gen(prefix)
        return f"{prefix}_{uuid.uuid4().hex}"


__all__ = [
    "AgentRuntime",
    "RuntimeConfig",
    "AgentDefinition",
    "RunContext",
    "RuntimeDeps",
    "Step",
    "RunResult",
]
