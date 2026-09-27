import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import RoleCreateRequest, RoleOut, RolePermissionBindRequest
from smartagent.api.security import get_current_user, require_admin
from smartagent.db.models import Permission, Role, RolePermission
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/roles", tags=["iam"])


def _to_out(role: Role) -> RoleOut:
    return RoleOut(id=role.id, tenant_id=role.tenant_id, name=role.name, is_builtin=role.is_builtin)


@router.post("", response_model=RoleOut, status_code=201)
async def create_role(
    body: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_admin),
):
    role = Role(id=f"role_{uuid.uuid4().hex}", tenant_id=principal.tenant_id, name=body.name, is_builtin=False)
    db.add(role)
    await db.flush()
    await _bind_permissions(db, role.id, body.permission_codes)
    await db.commit()
    await db.refresh(role)
    return _to_out(role)


@router.post("/{role_id}/permissions", response_model=RoleOut)
async def bind_permissions(
    role_id: str,
    body: RolePermissionBindRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_admin),
):
    role = await db.get(Role, role_id)
    if role is None or role.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": f"role {role_id} not found"})
    # Replace the existing permission set.
    await db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role_id))
    await _bind_permissions(db, role_id, body.permission_codes)
    await db.commit()
    return _to_out(role)


@router.get("", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    rows = (await db.execute(select(Role).where(Role.tenant_id == principal.tenant_id))).scalars().all()
    return [_to_out(r) for r in rows]


async def _bind_permissions(db: AsyncSession, role_id: str, codes: list[str]) -> None:
    """Resolve permission codes to ids and create RolePermission rows."""
    if not codes:
        return
    permissions = (await db.execute(select(Permission).where(Permission.code.in_(codes)))).scalars().all()
    for perm in permissions:
        db.add(RolePermission(role_id=role_id, permission_id=perm.id))
