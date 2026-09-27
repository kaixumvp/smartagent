"""Run endpoints: create (sync or SSE), fetch, and act on a run awaiting human approval.

Orchestration lives in `src.services.run_service`; this module is HTTP semantics only
— validate, enforce tenancy, persist the `runs` row, delegate, render.

HITL is mid-run (V0.2 close-out): a run executes until the execute node hits a resource whose
authorization comes back REQUIRE_APPROVAL, pauses as `awaiting_human`, and is continued in
place by `AgentRuntime.resume` once approved. Note the framework's authorization semantics
(`ouroboros.ports.check_permission`): admins are allowed outright and never trigger approval,
and a non-admin needs an explicit allow-grant on the resource or the decision is DENY rather
than REQUIRE_APPROVAL.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import write_audit
from smartagent.api.deps import (
    get_llm_gateway,
    get_memory_manager,
    get_permission_manager,
    get_tool_registry,
)
from smartagent.api.schemas import (
    PendingApprovalOut,
    RunActionRequest,
    RunCreateRequest,
    RunOut,
    StepOut,
    UsageOut,
)
from smartagent.api.security import get_current_user, get_permission_context, require_permission
from smartagent.api.sse import to_sse
from smartagent.config import Settings, get_settings
from smartagent.db.models import Agent, Run, RunStep
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import PermissionContext, Principal
from smartagent.services.experiment_service import ExperimentService, subject_key_for
from smartagent.services.run_service import RunService
from smartagent.util import new_id, utcnow
from src.events.events import run_failed
from src.llm.base import LLMGateway
from src.memory.manager import MemoryManager
from src.tools.registry import ToolRegistry

router = APIRouter(tags=["runs"])
logger = logging.getLogger(__name__)

# Closes the SSE drain loop even if the runtime dies before emitting a terminal event.
_STREAM_DONE = object()


def _not_found(resource: str, ident: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"{resource} {ident} not found"},
    )


def _invalid_state(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "INVALID_STATE", "message": message})


async def _load_steps(db: AsyncSession, run_id: str) -> list[RunStep]:
    return (
        await db.execute(select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.seq))
    ).scalars().all()


def _to_run_out(run: Run, steps: list[RunStep]) -> RunOut:
    usage = run.token_usage or {}
    return RunOut(
        run_id=run.id,
        agent_id=run.agent_id,
        status=run.status,
        result=run.result,
        steps=[
            StepOut(
                seq=s.seq,
                node=s.node,
                action=s.action,
                input=s.input,
                output=s.output,
                status=s.status,
                latency_ms=s.latency_ms,
            )
            for s in steps
        ],
        usage=UsageOut(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
        # Framework pending entries also carry `action`, which the response model does not
        # expose — map the fields explicitly rather than splatting.
        pending_approvals=[
            PendingApprovalOut(
                resource_type=p.get("resource_type", "tool"),
                resource_id=p.get("resource_id", ""),
            )
            for p in (run.pending_approvals or [])
        ],
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


async def _resolve_variant(
    db: AsyncSession,
    agent: Agent,
    principal: Principal,
    *,
    user_id: str | None,
    run_id: str,
) -> tuple[Agent, str | None, str | None]:
    """Swap in the caller's A/B variant when a running experiment fronts this agent.

    Returns the agent to actually run plus the experiment/variant to record. Falls through
    untouched when there is no experiment, or when the variant points at a missing agent —
    a misconfigured experiment must not break traffic.
    """
    service = ExperimentService(db)
    experiment = await service.find_running(principal.tenant_id, agent.id)
    if experiment is None:
        return agent, None, None

    subject = subject_key_for(user_id, principal.user_id, run_id)
    assignment = await service.assign(experiment, subject)
    variant_agent = await db.get(Agent, assignment.agent_id)
    if variant_agent is None or variant_agent.tenant_id != principal.tenant_id:
        logger.warning(
            "experiment %s variant %s points at missing agent %s; serving the entry agent",
            experiment.id, assignment.variant, assignment.agent_id,
        )
        return agent, experiment.id, None
    return variant_agent, experiment.id, assignment.variant


def _build_service(
    request: Request,
    db: AsyncSession,
    principal: Principal,
    perm_ctx: PermissionContext,
    llm: LLMGateway,
    memory: MemoryManager,
    settings: Settings,
    tool_registry: ToolRegistry,
) -> RunService:
    return RunService(
        db=db,
        llm=llm,
        memory=memory,
        settings=settings,
        principal=principal,
        permission_context=perm_ctx,
        permission_manager=get_permission_manager(),
        tool_registry=tool_registry,
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.post("/agents/{agent_id}/runs", response_model=RunOut)
async def create_run(
    agent_id: str,
    body: RunCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    _: None = Depends(require_permission("run:execute")),
    llm: LLMGateway = Depends(get_llm_gateway),
    registry_tools: ToolRegistry = Depends(get_tool_registry),
    memory: MemoryManager = Depends(get_memory_manager),
    settings: Settings = Depends(get_settings),
):
    if not body.input or not body.input.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "input must not be empty"},
        )

    agent = await db.get(Agent, agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id:
        raise _not_found("agent", agent_id)

    run_id = new_id("run")
    # A/B: if a running experiment fronts this agent, serve the caller's assigned variant.
    agent, experiment_id, variant = await _resolve_variant(
        db, agent, principal, user_id=body.user_id, run_id=run_id
    )

    service = _build_service(request, db, principal, perm_ctx, llm, memory, settings, registry_tools)
    registry = await service.load_registry(db, agent)

    run = Run(
        id=run_id,
        agent_id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=body.user_id,
        input=body.input,
        status="running",
        trace_id=getattr(request.state, "trace_id", None),
        experiment_id=experiment_id,
        variant=variant,
        created_at=utcnow(),
        started_at=utcnow(),
    )
    db.add(run)
    await db.commit()

    if body.stream:
        return StreamingResponse(
            _stream_run(service, agent, run, body, registry),
            media_type="text/event-stream",
        )

    result = await service.start(
        agent, run, task=body.input, user_id=body.user_id, registry=registry
    )
    await service.finalize(agent, run, result, user_id=body.user_id)
    return _to_run_out(run, await _load_steps(db, run.id))


async def _stream_run(service: RunService, agent: Agent, run: Run, body: RunCreateRequest, registry):
    """Drain runtime events into SSE frames, then finalize.

    Persisting from inside the generator is safe: FastAPI registers `yield` dependencies on
    the request-scoped exit stack (`fastapi_inner_astack`), which wraps the response send —
    so the `get_db` session outlives the stream. This is version-dependent behaviour, verified
    against FastAPI 0.141.1 (`fastapi/routing.py`).
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def produce():
        try:
            return await service.start(
                agent, run, task=body.input, user_id=body.user_id, registry=registry, queue=queue
            )
        finally:
            await queue.put(_STREAM_DONE)

    task = asyncio.create_task(produce())

    # `run.started` / `step.completed` / terminal events all arrive through the RunRecorder.
    while True:
        item = await queue.get()
        if item is _STREAM_DONE:
            break
        yield to_sse(item)

    try:
        result = await task
    except Exception as exc:  # noqa: BLE001 — the runtime escaped its own error handling
        logger.exception("streamed run failed: run_id=%s", run.id)
        await service.mark_failed(run, str(exc))
        yield to_sse(run_failed(run.id, str(exc)))
        return

    await service.finalize(agent, run, result, user_id=body.user_id)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != principal.tenant_id:
        raise _not_found("run", run_id)
    return _to_run_out(run, await _load_steps(db, run_id))


@router.post("/runs/{run_id}/actions", response_model=RunOut)
async def run_action(
    run_id: str,
    body: RunActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    _: None = Depends(require_permission("run:execute")),
    llm: LLMGateway = Depends(get_llm_gateway),
    registry_tools: ToolRegistry = Depends(get_tool_registry),
    memory: MemoryManager = Depends(get_memory_manager),
    settings: Settings = Depends(get_settings),
):
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != principal.tenant_id:
        raise _not_found("run", run_id)
    if run.status != "awaiting_human":
        raise _invalid_state(f"run {run_id} is not awaiting approval")

    trace_id = getattr(request.state, "trace_id", None)

    if body.action == "reject":
        run.status = "canceled"
        run.pending_approvals = None
        run.finished_at = utcnow()
        await db.commit()
        await write_audit(
            db,
            tenant_id=principal.tenant_id,
            action="run.reject",
            result="reject",
            actor=principal.user_id,
            resource_type="run",
            resource_id=run.id,
            trace_id=trace_id,
        )
        return _to_run_out(run, await _load_steps(db, run_id))

    if body.action != "approve":
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "action must be approve or reject"},
        )

    agent = await db.get(Agent, run.agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id:
        raise _not_found("agent", run.agent_id)

    pending = run.pending_approvals or []
    pending_ids = {p.get("resource_id") for p in pending if p.get("resource_id")}
    # An explicit resource_id approves just that one; omitting it approves everything pending.
    newly = {body.resource_id} if body.resource_id else pending_ids
    run.approvals = sorted(set(run.approvals or []) | newly)
    await db.commit()

    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="run.approve",
        result="approve",
        actor=principal.user_id,
        resource_type=body.resource_type or "tool",
        resource_id=body.resource_id,
        trace_id=trace_id,
        detail={"run_id": run.id, "approved": sorted(newly)},
    )

    remaining = pending_ids - newly
    if remaining:
        run.pending_approvals = [p for p in pending if p.get("resource_id") in remaining]
        await db.commit()
        return _to_run_out(run, await _load_steps(db, run_id))

    service = _build_service(request, db, principal, perm_ctx, llm, memory, settings, registry_tools)
    registry = await service.load_registry(db, agent)

    run.status = "running"
    run.pending_approvals = None
    await db.commit()

    try:
        result = await service.resume(agent, run, registry=registry, approvals=sorted(newly))
    except RuntimeError as exc:  # no checkpoint to resume from
        logger.warning("resume rejected: run_id=%s: %s", run_id, exc)
        raise _invalid_state(f"run {run_id} cannot be resumed: {exc}") from exc

    await service.finalize(agent, run, result, user_id=run.user_id)
    return _to_run_out(run, await _load_steps(db, run_id))
