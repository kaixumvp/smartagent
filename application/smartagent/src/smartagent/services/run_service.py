"""Run orchestration: assemble a framework run from persisted state, write the outcome back.

Everything the framework needs (`AgentDefinition` / `RunContext` / `RuntimeDeps`) is derived
here from the Agent row plus `Settings`, and everything it produces (`RunResult`) is folded
back into `runs` / `run_steps` / long-term memory / `audit_logs`.

Three framework contract details this module exists to get right — each one is a silent bug
if handled the obvious way instead:

1. `AgentRuntime._initial_state` uses `history` *verbatim* when it is non-empty and does NOT
   append the task. So the current user turn must be written into the Working Brain BEFORE
   history is read, or from turn two onward the user's input never reaches the LLM.
2. `AgentRuntime._recall_context` recalls on its own when `deps.long_term_memory` is set, and
   prepends that to `memory_context`. Passing both double-injects every memory. We recall
   host-side (honouring `settings.memory_recall_top_k`, and keeping the `get_memory_manager`
   test seam) and deliberately leave `deps.long_term_memory` unset. Trade-off: the framework's
   Knowledge fallback stays dormant until the business layer implements that port in V0.3.
3. The runtime deliberately does not checkpoint the paused state; the last snapshot is
   post-decide with `_next_node == "execute"`, which is exactly the step `resume` re-runs.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import AuditingPermissionChecker, flush_permission_decisions, write_audit
from smartagent.adapters.cost_gateway import RunScopedRoutingGateway
from smartagent.adapters.db_checkpointer import DbCheckpointer
from smartagent.adapters.db_plugin_loader import PluginLoader
from smartagent.adapters.run_recorder import RunRecorder
from smartagent.adapters.subagent_runner import DbSubagentRunner
from smartagent.config import Settings
from smartagent.db.models import Agent, Run, RunStep
from smartagent.util import new_id, utcnow
from ouroboros.core.runtime import (
    AgentDefinition,
    AgentRuntime,
    RunContext,
    RunResult,
    RuntimeConfig,
    RuntimeDeps,
)
from ouroboros.plugins.registry import PluginRegistry
from ouroboros.skills.manager import SkillManager

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"completed", "failed", "canceled"}


class RunService:
    """Drives one HTTP request's worth of agent execution."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        llm,
        memory,
        settings: Settings,
        principal,
        permission_context,
        permission_manager,
        tool_registry,
        trace_id: str | None = None,
        memory_write_back: bool = True,
    ) -> None:
        self._db = db
        self._llm = llm
        self._memory = memory
        self._settings = settings
        self._principal = principal
        self._permission_context = permission_context
        self._trace_id = trace_id
        # Evaluation is a synthetic workload; folding its answers into long-term memory would
        # poison real users' recall, so the eval service turns this off.
        self._memory_write_back = memory_write_back
        self._runtime = AgentRuntime()
        self._checker = AuditingPermissionChecker(permission_manager)
        # run_id -> the per-run gateway holding that run's cost ledger, popped by `finalize`.
        self._gateways: dict[str, RunScopedRoutingGateway] = {}

        # `_run_child` reads `self._loader`, and the loader is built from a SkillManager that
        # needs the sub-agent runner — a cycle. Binding the method here defers the read to
        # call time, which is always after __init__ returns. (V0.2 used a `loader_holder`
        # dict for this; holding the state on the service instance makes it unnecessary.)
        self._subagent_runner = DbSubagentRunner(
            principal=principal, settings=settings, child_runner=self._run_child
        )
        self._loader = PluginLoader(tool_registry, SkillManager(run_subagent=self._subagent_runner))

    # ------------------------------------------------------------------ assembly
    async def load_registry(self, db: AsyncSession, agent: Agent) -> PluginRegistry:
        return await self._loader.load_for_agent(db, self._principal.tenant_id, agent.config)

    def build_runtime_config(self, agent_config: dict | None) -> RuntimeConfig:
        """Agent-level `config.runtime` overrides the deployment-wide `Settings` defaults."""
        runtime = (agent_config or {}).get("runtime") or {}
        settings = self._settings
        return RuntimeConfig(
            max_iterations=int(runtime.get("max_iterations", settings.max_iterations)),
            timeout_seconds=float(runtime.get("timeout_seconds", settings.timeout_seconds)),
            max_subagent_depth=int(runtime.get("max_subagent_depth", settings.max_subagent_depth)),
            max_total_tokens=int(runtime.get("max_total_tokens", 0)),  # 0 = unlimited
        )

    def build_definition(self, agent: Agent, registry: PluginRegistry) -> AgentDefinition:
        config = agent.config or {}
        return AgentDefinition(
            # Empty means "the agent pinned no model" — the per-run gateway then decides
            # (tiered routing, else the deployment default). Resolving to `settings.llm_model`
            # here instead would make every model concrete and permanently disable routing,
            # because the runtime forwards this value to every node (runtime.py:249).
            model=config.get("model") or "",
            system_prompt=config.get("system_prompt"),
            plugins=registry.all(),
            runtime=self.build_runtime_config(config),
            agent_id=agent.id,
        )

    def _build_gateway(self, run_id: str) -> RunScopedRoutingGateway:
        settings = self._settings
        gateway = RunScopedRoutingGateway(
            self._llm,
            default_model=settings.llm_model,
            routing_enabled=settings.llm_routing_enabled,
            cheap_model=settings.llm_cheap_model,
            expensive_model=settings.llm_expensive_model,
            threshold=settings.llm_routing_threshold,
            price_overrides=settings.model_prices,
        )
        self._gateways[run_id] = gateway
        return gateway

    def _build_deps(self, db: AsyncSession, event_sink, gateway) -> RuntimeDeps:
        return RuntimeDeps(
            llm=gateway,
            permission_checker=self._checker,
            permission_context=self._permission_context,
            checkpointer=DbCheckpointer(db),
            event_sink=event_sink,
            subagent_runner=self._subagent_runner,
            db=db,
            id_gen=new_id,  # framework-minted ids keep the business `{prefix}_{hex}` convention
            # long_term_memory intentionally unset — see module docstring, note 2.
        )

    def session_id(self, agent: Agent, run: Run, user_id: str | None) -> str:
        """Working Brain key. Falls back to a per-run key for anonymous callers."""
        return user_id or f"{agent.id}:{run.id}"

    # ------------------------------------------------------------------ execution
    async def start(
        self,
        agent: Agent,
        run: Run,
        *,
        task: str,
        user_id: str | None,
        registry: PluginRegistry,
        queue=None,
    ) -> RunResult:
        session_id = self.session_id(agent, run, user_id)
        # Order matters — see module docstring, note 1.
        await self._memory.write(session_id, {"role": "user", "content": task})
        history = await self._memory.get_history(session_id)
        memory_ctx = await self._recall(task, user_id)

        deps = self._build_deps(
            self._db, RunRecorder(self._db, run.id, queue=queue), self._build_gateway(run.id)
        )
        context = RunContext(
            tenant_id=self._principal.tenant_id,
            user_id=user_id,
            session_id=session_id,
            run_id=run.id,
            subagent_depth=0,
        )
        return await self._runtime.run(
            self.build_definition(agent, registry),
            task,
            context,
            deps,
            history=history,
            memory_context=memory_ctx,
            approvals=list(run.approvals or []),
        )

    async def resume(
        self,
        agent: Agent,
        run: Run,
        *,
        registry: PluginRegistry,
        approvals: list[str],
    ) -> RunResult:
        """Continue a paused run in place, re-running only the step that blocked on approval."""
        # The framework numbers steps from 1 on every call, so a resume has to pick up where
        # the paused half of the timeline left off.
        recorder = RunRecorder(self._db, run.id, seq_offset=await self._max_step_seq(run.id))
        deps = self._build_deps(self._db, recorder, self._build_gateway(run.id))
        return await self._runtime.resume(self.build_definition(agent, registry), run.id, approvals, deps)

    async def _max_step_seq(self, run_id: str) -> int:
        steps = (
            await self._db.execute(select(RunStep).where(RunStep.run_id == run_id))
        ).scalars().all()
        return max((s.seq or 0) for s in steps) if steps else 0

    async def _recall(self, query: str, user_id: str | None) -> list[dict]:
        try:
            entries = await self._memory.recall(
                self._db,
                self._principal.tenant_id,
                user_id,
                query,
                top_k=self._settings.memory_recall_top_k,
            )
        except Exception:  # noqa: BLE001 — recall is an enhancement, not a precondition
            logger.warning("long-term recall failed", exc_info=True)
            return []
        return [{"content": e.content, "similarity": e.similarity} for e in entries]

    # ------------------------------------------------------------------ sub-agents
    async def _run_child(
        self,
        agent: Agent,
        task: str,
        ctx,
        db: AsyncSession,
        run: Run,
    ) -> RunResult:
        """ChildRunner for `DbSubagentRunner`: everything is bound to the child's own session."""
        registry = await self.load_registry(db, agent)
        gateway = self._build_gateway(run.id)
        deps = self._build_deps(db, RunRecorder(db, run.id), gateway)
        context = RunContext(
            tenant_id=self._principal.tenant_id,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            run_id=run.id,
            subagent_depth=ctx.subagent_depth + 1,
        )
        result = await self._runtime.run(
            self.build_definition(agent, registry),
            task,
            context,
            deps,
            memory_context=await self._recall(task, ctx.user_id),
        )
        run.token_usage = result.token_usage
        self._apply_cost(run)
        await db.commit()
        return result

    def _apply_cost(self, run: Run) -> None:
        """Attribute the run's model and spend from its own gateway ledger."""
        gateway = self._gateways.pop(run.id, None)
        if gateway is None:
            return
        run.model = gateway.model
        run.cost = gateway.cost

    # ------------------------------------------------------------------ outcome
    async def finalize(
        self,
        agent: Agent,
        run: Run,
        result: RunResult,
        *,
        user_id: str | None,
    ) -> None:
        """Fold a RunResult back into persistence, memory, and the audit trail.

        `RunRecorder` already applied status/result/error/pending_approvals from the terminal
        event; this backstops what the event cannot carry and runs the business-policy bits.
        """
        if run.status not in TERMINAL_STATUSES and run.status != "awaiting_human":
            # No terminal event reached the sink (e.g. the runtime raised past it).
            run.status = result.status
            run.result = result.result
            run.error = result.error
            if result.status in TERMINAL_STATUSES:
                run.finished_at = utcnow()
        run.token_usage = result.token_usage
        self._apply_cost(run)
        await self._db.commit()

        if result.status == "awaiting_human":
            await write_audit(
                self._db,
                tenant_id=self._principal.tenant_id,
                action="run.awaiting_human",
                result="require_approval",
                actor=self._principal.user_id,
                resource_type="agent",
                resource_id=run.agent_id,
                trace_id=self._trace_id,
                detail={"run_id": run.id, "pending_approvals": result.pending_approvals},
            )
        else:
            # Only persist the turn once it actually produced an answer; a paused run would
            # otherwise write an empty assistant message into the session history.
            await self._write_back(agent, run, result, user_id)

        await flush_permission_decisions(
            self._db,
            self._checker,
            tenant_id=self._principal.tenant_id,
            actor=self._principal.user_id,
            run_id=run.id,
            trace_id=self._trace_id,
        )

    async def _write_back(self, agent: Agent, run: Run, result: RunResult, user_id: str | None) -> None:
        """Persist the assistant turn and consolidate long-term memory (both best-effort)."""
        if not self._memory_write_back:
            return
        session_id = self.session_id(agent, run, user_id)
        try:
            await self._memory.write(session_id, {"role": "assistant", "content": result.result or ""})
        except Exception:  # noqa: BLE001
            logger.warning("working-memory write-back failed: run_id=%s", run.id, exc_info=True)
        try:
            await self._memory.consolidate(self._db, session_id, self._principal.tenant_id, user_id)
        except Exception:  # noqa: BLE001
            logger.warning("memory consolidation failed: run_id=%s", run.id, exc_info=True)

    async def mark_failed(self, run: Run, error: str) -> None:
        """Terminal failure that happened outside the runtime (so no `run.failed` was emitted)."""
        run.status = "failed"
        run.error = error
        run.finished_at = utcnow()
        await self._db.commit()
