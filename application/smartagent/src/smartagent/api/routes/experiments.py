"""A/B experiment endpoints: define a split, start/stop it, compare the variants."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import (
    ExperimentCreateRequest,
    ExperimentOut,
    ExperimentResultsOut,
    ExperimentStatusRequest,
    VariantIn,
    VariantStatsOut,
)
from smartagent.api.security import get_current_user, require_permission
from smartagent.db.models import Agent, AgentExperiment, Feedback, Run
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from smartagent.util import new_id, utcnow

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _not_found(ident: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"experiment {ident} not found"},
    )


def _to_out(experiment: AgentExperiment) -> ExperimentOut:
    return ExperimentOut(
        id=experiment.id,
        tenant_id=experiment.tenant_id,
        name=experiment.name,
        description=experiment.description,
        entry_agent_id=experiment.entry_agent_id,
        status=experiment.status,
        variants=[VariantIn(**v) for v in (experiment.variants or [])],
        sticky_key=experiment.sticky_key,
        created_at=experiment.created_at,
    )


@router.post("", response_model=ExperimentOut, status_code=201)
async def create_experiment(
    body: ExperimentCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("experiment:manage")),
):
    if len(body.variants) < 2:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "an experiment needs at least two variants"},
        )
    if sum(v.weight for v in body.variants) <= 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "variant weights must sum to more than zero"},
        )

    entry = await db.get(Agent, body.entry_agent_id)
    if entry is None or entry.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {body.entry_agent_id} not found"},
        )
    for variant in body.variants:
        agent = await db.get(Agent, variant.agent_id)
        if agent is None or agent.tenant_id != principal.tenant_id:
            raise HTTPException(
                status_code=404,
                detail={"code": "RESOURCE_NOT_FOUND", "message": f"agent {variant.agent_id} not found"},
            )

    experiment = AgentExperiment(
        id=new_id("exp"),
        tenant_id=principal.tenant_id,
        name=body.name,
        description=body.description,
        entry_agent_id=body.entry_agent_id,
        status="draft",
        variants=[v.model_dump() for v in body.variants],
        sticky_key=body.sticky_key,
        created_by=principal.user_id,
    )
    db.add(experiment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "INVALID_STATE", "message": f"experiment '{body.name}' already exists"},
        ) from None
    return _to_out(experiment)


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("experiment:view")),
):
    rows = (
        await db.execute(
            select(AgentExperiment).where(AgentExperiment.tenant_id == principal.tenant_id)
        )
    ).scalars().all()
    return [_to_out(row) for row in rows]


@router.post("/{experiment_id}/status", response_model=ExperimentOut)
async def set_status(
    experiment_id: str,
    body: ExperimentStatusRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("experiment:manage")),
):
    experiment = await db.get(AgentExperiment, experiment_id)
    if experiment is None or experiment.tenant_id != principal.tenant_id:
        raise _not_found(experiment_id)

    if body.action == "start":
        if experiment.status == "stopped":
            # Restarting would reuse assignments made under the old split; make it explicit
            # that a new split means a new experiment.
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_STATE", "message": "a stopped experiment cannot be restarted"},
            )
        experiment.status = "running"
        experiment.started_at = experiment.started_at or utcnow()
    elif body.action == "stop":
        experiment.status = "stopped"
        experiment.stopped_at = utcnow()
    else:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "action must be start or stop"},
        )

    await db.commit()
    return _to_out(experiment)


@router.get("/{experiment_id}/results", response_model=ExperimentResultsOut)
async def get_results(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("experiment:view")),
):
    experiment = await db.get(AgentExperiment, experiment_id)
    if experiment is None or experiment.tenant_id != principal.tenant_id:
        raise _not_found(experiment_id)

    runs = (
        await db.execute(select(Run).where(Run.experiment_id == experiment_id))
    ).scalars().all()
    run_ids = {r.id for r in runs}
    feedbacks = (
        await db.execute(select(Feedback).where(Feedback.run_id.in_(run_ids)))
    ).scalars().all() if run_ids else []

    ratings: dict[str, list[int]] = {}
    run_variant = {r.id: (r.variant or "?") for r in runs}
    for feedback in feedbacks:
        ratings.setdefault(run_variant.get(feedback.run_id, "?"), []).append(feedback.rating)

    stats: list[VariantStatsOut] = []
    for variant in experiment.variants or []:
        label = str(variant.get("label") or variant.get("agent_id") or "?")
        bucket = [r for r in runs if (r.variant or "?") == label]
        completed = [r for r in bucket if r.status == "completed"]
        latencies = [
            int((r.finished_at - r.started_at).total_seconds() * 1000)
            for r in completed
            if r.finished_at and r.started_at
        ]
        variant_ratings = ratings.get(label, [])
        stats.append(
            VariantStatsOut(
                variant=label,
                agent_id=variant.get("agent_id"),
                runs=len(bucket),
                completed=len(completed),
                failed=len([r for r in bucket if r.status == "failed"]),
                avg_cost=round(sum(float(r.cost or 0) for r in bucket) / len(bucket), 6) if bucket else 0.0,
                avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
                feedback_count=len(variant_ratings),
                avg_rating=round(sum(variant_ratings) / len(variant_ratings), 3) if variant_ratings else None,
            )
        )

    return ExperimentResultsOut(experiment_id=experiment.id, status=experiment.status, variants=stats)
