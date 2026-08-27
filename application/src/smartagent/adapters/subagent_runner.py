"""Nested agent runs (business adapter).

Implements the framework `SubagentRunner` port (`ouroboros.ports`): when an agent-skill in a
parent run delegates to another Agent, that delegation becomes a child `runs` row linked by
`parent_run_id`, so the whole tree stays traceable.

This adapter owns the *persistence* shape of a nested run (resolve the agent, guard the
depth, open a session, create and close the child row). Assembling the framework definition
and deps is the caller's job, injected as `child_runner`.
"""

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.config import Settings
from smartagent.db.models import Agent, Run
from smartagent.db.session import SessionLocal
from smartagent.util import new_id, utcnow
from ouroboros.core.runtime import RunResult
from ouroboros.ports import InvokeContext, Principal

logger = logging.getLogger(__name__)

# (child agent, task, parent invoke context, session owning the child run, child run row)
ChildRunner = Callable[[Agent, str, InvokeContext, AsyncSession, Run], Awaitable[RunResult]]


class DbSubagentRunner:
    """Runs a referenced Agent as a child run and returns its answer to the parent."""

    def __init__(
        self,
        *,
        principal: Principal,
        settings: Settings,
        child_runner: ChildRunner,
        session_factory=SessionLocal,
    ) -> None:
        self._principal = principal
        self._settings = settings
        self._child_runner = child_runner
        self._session_factory = session_factory

    async def __call__(self, agent_ref: str, task: str, ctx: InvokeContext) -> str:
        # Belt and braces: the framework's execute node caps depth too (core/nodes/execute.py),
        # but a nested run is expensive enough to refuse before touching the database.
        if ctx.subagent_depth >= self._settings.max_subagent_depth:
            logger.warning("sub-agent refused: depth=%s ref=%s", ctx.subagent_depth, agent_ref)
            return "max sub-agent depth reached"

        # A child run gets its own session. The framework executes all tool calls of one round
        # concurrently (`asyncio.gather` in core/nodes/execute.py), so two agent-skills can
        # land here in parallel — and an AsyncSession is not safe for concurrent use.
        async with self._session_factory() as db:
            agent = await db.get(Agent, agent_ref)
            if agent is None or agent.tenant_id != self._principal.tenant_id:
                return f"sub-agent {agent_ref} not found"

            run = Run(
                id=new_id("run"),
                agent_id=agent.id,
                tenant_id=self._principal.tenant_id,
                user_id=ctx.user_id,
                input=task,
                status="running",
                trace_id=ctx.trace_id,
                parent_run_id=ctx.run_id,
                created_at=utcnow(),
                started_at=utcnow(),
            )
            db.add(run)
            await db.commit()

            try:
                result = await self._child_runner(agent, task, ctx, db, run)
            except Exception as exc:  # noqa: BLE001 — report upward, never leave the row "running"
                logger.exception("sub-agent run failed: run_id=%s ref=%s", run.id, agent_ref)
                await db.rollback()
                run.status = "failed"
                run.error = str(exc)
                run.finished_at = utcnow()
                await db.commit()
                return f"[sub-agent failed] {exc}"

            return _to_parent_message(result)


def _to_parent_message(result: RunResult) -> str:
    """Render a child RunResult as the string the parent's Observe node will reflect on."""
    if result.status == "completed":
        return result.result or ""
    if result.status == "awaiting_human":
        pending = ", ".join(p.get("resource_id", "?") for p in result.pending_approvals)
        return f"[sub-agent paused] awaiting approval for: {pending}"
    return f"[sub-agent {result.status}] {result.error or ''}".strip()
