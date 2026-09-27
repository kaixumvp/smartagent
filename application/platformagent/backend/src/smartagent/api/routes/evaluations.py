"""Evaluation endpoints: launch an offline evaluation, then poll it.

Creation returns 202 immediately — a golden set is N full agent runs, which would blow any
sane HTTP timeout. The job itself lives in `services/evaluation_service.py`.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.deps import get_judge_gateway, get_llm_gateway, get_memory_manager, get_tool_registry
from smartagent.api.schemas import EvaluationCreateRequest, EvaluationOut, EvaluationResultOut
from smartagent.api.security import get_current_user, require_permission
from smartagent.config import Settings, get_settings
from smartagent.db.models import Agent, Evaluation, EvaluationResult, GoldenSet
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from smartagent.services.evaluation_service import EvaluationJob, launch
from smartagent.util import new_id
from src.memory.manager import MemoryManager
from src.tools.registry import ToolRegistry

router = APIRouter(prefix="/evaluations", tags=["evaluation"])
logger = logging.getLogger(__name__)


def _not_found(ident: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"evaluation {ident} not found"},
    )


def _to_out(evaluation: Evaluation, results: list[EvaluationResult]) -> EvaluationOut:
    return EvaluationOut(
        id=evaluation.id,
        tenant_id=evaluation.tenant_id,
        golden_set_id=evaluation.golden_set_id,
        agent_id=evaluation.agent_id,
        status=evaluation.status,
        judge_type=evaluation.judge_type,
        judge_model=evaluation.judge_model,
        total=evaluation.total,
        passed=evaluation.passed,
        failed=evaluation.failed,
        avg_score=float(evaluation.avg_score or 0),
        cost=float(evaluation.cost or 0),
        error=evaluation.error,
        results=[
            EvaluationResultOut(
                case_id=r.case_id,
                run_id=r.run_id,
                output=r.output,
                score=float(r.score or 0),
                passed=r.passed,
                reason=r.reason,
                latency_ms=r.latency_ms,
                cost=float(r.cost or 0),
                error=r.error,
            )
            for r in results
        ],
        created_at=evaluation.created_at,
        started_at=evaluation.started_at,
        finished_at=evaluation.finished_at,
    )


@router.post("", response_model=EvaluationOut, status_code=202)
async def create_evaluation(
    body: EvaluationCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("eval:manage")),
    memory: MemoryManager = Depends(get_memory_manager),
    registry_tools: ToolRegistry = Depends(get_tool_registry),
    settings: Settings = Depends(get_settings),
):
    golden_set = await db.get(GoldenSet, body.golden_set_id)
    if golden_set is None or golden_set.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"golden set {body.golden_set_id} not found"},
        )
    agent = await db.get(Agent, body.agent_id)
    if agent is None or agent.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {body.agent_id} not found"},
        )
    if body.judge_type not in {"llm", "heuristic"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "judge_type must be llm or heuristic"},
        )

    evaluation = Evaluation(
        id=new_id("eval"),
        tenant_id=principal.tenant_id,
        golden_set_id=golden_set.id,
        agent_id=agent.id,
        status="queued",
        judge_type=body.judge_type,
        judge_model=body.judge_model or settings.judge_model or settings.llm_model,
        created_by=principal.user_id,
    )
    db.add(evaluation)
    await db.commit()

    # The job gets its own sessions; nothing tied to this request survives into it.
    launch(
        EvaluationJob(
            evaluation_id=evaluation.id,
            principal=principal,
            settings=settings,
            llm=get_llm_gateway(),
            judge_gateway=get_judge_gateway(),
            memory=memory,
            tool_registry=registry_tools,
        )
    )
    return _to_out(evaluation, [])


@router.get("", response_model=list[EvaluationOut])
async def list_evaluations(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("eval:view")),
):
    rows = (
        await db.execute(
            select(Evaluation)
            .where(Evaluation.tenant_id == principal.tenant_id)
            .order_by(Evaluation.created_at.desc())
        )
    ).scalars().all()
    return [_to_out(row, []) for row in rows]


@router.get("/{evaluation_id}", response_model=EvaluationOut)
async def get_evaluation(
    evaluation_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("eval:view")),
):
    evaluation = await db.get(Evaluation, evaluation_id)
    if evaluation is None or evaluation.tenant_id != principal.tenant_id:
        raise _not_found(evaluation_id)
    results = (
        await db.execute(
            select(EvaluationResult)
            .where(EvaluationResult.evaluation_id == evaluation_id)
            .order_by(EvaluationResult.created_at, EvaluationResult.id)
        )
    ).scalars().all()
    return _to_out(evaluation, results)
