"""Cost endpoints: where the money went, and how much the prompt cache saved.

`runs.cost` is only meaningful from V1.1 onward — the column existed since Alembic 0001 but
nothing wrote it, so any run created before this version reports 0.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.deps import get_llm_gateway
from smartagent.api.schemas import CacheStatsOut, CostBucketOut, CostSummaryOut
from smartagent.api.security import get_current_user, require_permission
from smartagent.config import Settings, get_settings
from smartagent.db.models import Run
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/cost", tags=["cost"])

_GROUPS = {
    "agent": lambda run: run.agent_id,
    "model": lambda run: run.model or "(unrecorded)",
    "experiment": lambda run: run.experiment_id or "(none)",
}


@router.get("/summary", response_model=CostSummaryOut)
async def cost_summary(
    group_by: str = "agent",
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("run:view")),
):
    key_of = _GROUPS.get(group_by)
    if key_of is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_ARGUMENT",
                "message": f"group_by must be one of {', '.join(_GROUPS)}",
            },
        )

    runs = (
        await db.execute(select(Run).where(Run.tenant_id == principal.tenant_id))
    ).scalars().all()

    buckets: dict[str, CostBucketOut] = {}
    for run in runs:
        bucket = buckets.setdefault(key_of(run), CostBucketOut(key=key_of(run)))
        bucket.runs += 1
        bucket.total_cost = round(bucket.total_cost + float(run.cost or 0), 6)
        bucket.total_tokens += (run.token_usage or {}).get("total_tokens", 0)

    ordered = sorted(buckets.values(), key=lambda b: b.total_cost, reverse=True)
    return CostSummaryOut(
        group_by=group_by,
        total_cost=round(sum(b.total_cost for b in ordered), 6),
        total_runs=len(runs),
        buckets=ordered,
    )


@router.get("/cache", response_model=CacheStatsOut)
async def cache_stats(
    _principal: Principal = Depends(get_current_user),
    __: None = Depends(require_permission("run:view")),
    settings: Settings = Depends(get_settings),
):
    """Prompt-cache hit rate, read off the process-wide `CachingGateway`.

    Process-local by design: the cache is in-memory, so numbers are per worker, not global.
    """
    gateway = get_llm_gateway()
    hits = getattr(gateway, "hits", 0)
    misses = getattr(gateway, "misses", 0)
    total = hits + misses
    return CacheStatsOut(
        enabled=settings.llm_cache_enabled,
        hits=hits,
        misses=misses,
        hit_rate=round(hits / total, 4) if total else 0.0,
        size=len(getattr(gateway, "_cache", ()) or ()),
    )
