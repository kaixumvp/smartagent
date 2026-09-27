"""Online feedback on a run — the production-traffic half of the evaluation signal.

No dedicated permission point: feedback is about the caller's own experience, so being
authenticated (and able to see the run) is the bar.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import FeedbackCreateRequest, FeedbackOut
from smartagent.api.security import get_current_user
from smartagent.db.models import Feedback, Run
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from smartagent.util import new_id

router = APIRouter(tags=["evaluation"])


def _to_out(feedback: Feedback) -> FeedbackOut:
    return FeedbackOut(
        id=feedback.id,
        run_id=feedback.run_id,
        user_id=feedback.user_id,
        rating=feedback.rating,
        comment=feedback.comment,
        tags=feedback.tags or [],
        created_at=feedback.created_at,
    )


async def _load_run(db: AsyncSession, run_id: str, principal: Principal) -> Run:
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != principal.tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": f"run {run_id} not found"},
        )
    return run


@router.post("/runs/{run_id}/feedback", response_model=FeedbackOut, status_code=201)
async def submit_feedback(
    run_id: str,
    body: FeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    run = await _load_run(db, run_id, principal)
    feedback = Feedback(
        id=new_id("fb"),
        tenant_id=run.tenant_id,
        run_id=run.id,
        user_id=run.user_id or principal.user_id,
        rating=body.rating,
        comment=body.comment,
        tags=body.tags,
    )
    db.add(feedback)
    await db.commit()
    return _to_out(feedback)


@router.get("/runs/{run_id}/feedback", response_model=list[FeedbackOut])
async def list_feedback(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    await _load_run(db, run_id, principal)
    rows = (
        await db.execute(
            select(Feedback).where(Feedback.run_id == run_id).order_by(Feedback.created_at)
        )
    ).scalars().all()
    return [_to_out(row) for row in rows]
