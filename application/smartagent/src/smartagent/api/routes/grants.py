import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import GrantCreateRequest, GrantOut
from smartagent.api.security import get_current_user, require_admin
from smartagent.db.models import Grant
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/grants", tags=["iam"])


def _to_out(grant: Grant) -> GrantOut:
    return GrantOut(
        id=grant.id,
        tenant_id=grant.tenant_id,
        principal_type=grant.principal_type,
        principal_id=grant.principal_id,
        resource_type=grant.resource_type,
        resource_id=grant.resource_id,
        action=grant.action,
        effect=grant.effect,
    )


@router.post("", response_model=GrantOut, status_code=201)
async def create_grant(
    body: GrantCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_admin),
):
    grant = Grant(
        id=f"grant_{uuid.uuid4().hex}",
        tenant_id=principal.tenant_id,
        principal_type=body.principal_type,
        principal_id=body.principal_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        action=body.action,
        effect=body.effect,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)
    return _to_out(grant)


@router.get("", response_model=list[GrantOut])
async def list_grants(
    principal_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    stmt = select(Grant).where(Grant.tenant_id == principal.tenant_id)
    if principal_id:
        stmt = stmt.where(Grant.principal_id == principal_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_out(g) for g in rows]


@router.delete("/{grant_id}", status_code=204)
async def delete_grant(
    grant_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_admin),
):
    grant = await db.get(Grant, grant_id)
    if grant is None or grant.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": f"grant {grant_id} not found"})
    await db.delete(grant)
    await db.commit()
