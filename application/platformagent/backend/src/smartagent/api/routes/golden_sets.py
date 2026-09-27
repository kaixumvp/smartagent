"""Golden set endpoints: the regression suites an agent must keep passing across versions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import GoldenCaseOut, GoldenSetCreateRequest, GoldenSetOut
from smartagent.api.security import get_current_user, require_permission
from smartagent.db.models import GoldenCase, GoldenSet
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal
from smartagent.util import new_id

router = APIRouter(prefix="/golden-sets", tags=["evaluation"])


def _to_out(golden_set: GoldenSet, cases: list[GoldenCase]) -> GoldenSetOut:
    return GoldenSetOut(
        id=golden_set.id,
        tenant_id=golden_set.tenant_id,
        name=golden_set.name,
        description=golden_set.description,
        status=golden_set.status,
        cases=[
            GoldenCaseOut(id=c.id, task=c.task, reference=c.reference, meta=c.meta) for c in cases
        ],
        created_at=golden_set.created_at,
    )


def _not_found(ident: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"golden set {ident} not found"},
    )


async def _load_cases(db: AsyncSession, golden_set_id: str) -> list[GoldenCase]:
    return (
        await db.execute(
            select(GoldenCase)
            .where(GoldenCase.golden_set_id == golden_set_id)
            .order_by(GoldenCase.created_at, GoldenCase.id)
        )
    ).scalars().all()


@router.post("", response_model=GoldenSetOut, status_code=201)
async def create_golden_set(
    body: GoldenSetCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("eval:manage")),
):
    if not body.cases:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ARGUMENT", "message": "a golden set needs at least one case"},
        )

    golden_set = GoldenSet(
        id=new_id("gset"),
        tenant_id=principal.tenant_id,
        name=body.name,
        description=body.description,
        status="active",
        owner=principal.user_id,
    )
    db.add(golden_set)
    cases = [
        GoldenCase(
            id=new_id("gcase"),
            golden_set_id=golden_set.id,
            task=case.task,
            reference=case.reference,
            meta=case.meta,
        )
        for case in body.cases
    ]
    for case in cases:
        db.add(case)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "INVALID_STATE", "message": f"golden set '{body.name}' already exists"},
        ) from None
    return _to_out(golden_set, cases)


@router.get("", response_model=list[GoldenSetOut])
async def list_golden_sets(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    rows = (
        await db.execute(select(GoldenSet).where(GoldenSet.tenant_id == principal.tenant_id))
    ).scalars().all()
    # Listing omits cases; fetch a single set to see them.
    return [_to_out(row, []) for row in rows]


@router.get("/{golden_set_id}", response_model=GoldenSetOut)
async def get_golden_set(
    golden_set_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    golden_set = await db.get(GoldenSet, golden_set_id)
    if golden_set is None or golden_set.tenant_id != principal.tenant_id:
        raise _not_found(golden_set_id)
    return _to_out(golden_set, await _load_cases(db, golden_set_id))
