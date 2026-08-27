"""User administration.

There is **no self-service registration**: this is a multi-tenant platform where an account
only means something inside a tenant, with roles and resource grants attached. Accounts are
created by someone holding `user:manage` — which, until now, was a permission code seeded by
Alembic 0002 with no endpoint behind it.

Guarded by `require_permission("user:manage")` rather than `require_admin`: the dependency
already short-circuits for admins (`api/security.py`), so admins keep full access, and user
administration additionally becomes delegable to a non-admin role.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import write_audit
from smartagent.api.schemas import (
    PasswordResetRequest,
    UserCreateRequest,
    UserOut,
    UserUpdateRequest,
)
from smartagent.api.security import get_current_user, hash_password, require_permission
from smartagent.db.models import Role, User, UserRole
from smartagent.db.session import get_db
from smartagent.iam import rbac
from smartagent.iam.permission_manager import Principal
from smartagent.util import new_id

router = APIRouter(prefix="/users", tags=["iam"])

_VALID_STATUSES = {"active", "disabled"}


def _not_found(user_id: str) -> HTTPException:
    # 404 rather than 403 for a cross-tenant id: 403 would confirm the account exists.
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": f"user {user_id} not found"},
    )


def _invalid(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "INVALID_ARGUMENT", "message": message})


def _to_out(user: User, roles: list[str]) -> UserOut:
    return UserOut(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        name=user.name,
        status=user.status,
        roles=roles,
        created_at=user.created_at,
    )


async def _load_user(db: AsyncSession, user_id: str, principal: Principal) -> User:
    user = await db.get(User, user_id)
    if user is None or user.tenant_id != principal.tenant_id:
        raise _not_found(user_id)
    return user


async def _resolve_roles(db: AsyncSession, tenant_id: str, names: list[str]) -> list[Role]:
    """Map role names to rows within the tenant, refusing unknown names.

    Deliberately stricter than `roles.py::_bind_permissions`, which drops unresolved codes
    silently — a typo there produces an account with fewer permissions than intended and no
    signal that anything went wrong.
    """
    if not names:
        return []
    rows = (
        await db.execute(select(Role).where(Role.tenant_id == tenant_id, Role.name.in_(names)))
    ).scalars().all()
    unknown = sorted(set(names) - {r.name for r in rows})
    if unknown:
        raise _invalid(f"unknown role(s): {', '.join(unknown)}")
    return rows


async def _set_roles(db: AsyncSession, user_id: str, roles: list[Role]) -> None:
    """Replace the user's role set."""
    await db.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
    for role in roles:
        db.add(UserRole(user_id=user_id, role_id=role.id))


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("user:manage")),
):
    roles = await _resolve_roles(db, principal.tenant_id, body.roles)

    user = User(
        id=new_id("user"),
        tenant_id=principal.tenant_id,  # always the caller's tenant; there is no cross-tenant path
        name=body.name or body.username,
        username=body.username,
        password_hash=hash_password(body.password),
        status="active",
    )
    db.add(user)
    try:
        await db.flush()
        await _set_roles(db, user.id, roles)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INVALID_STATE",
                "message": f"username '{body.username}' already exists in this tenant",
            },
        ) from None

    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="user.create",
        result="allow",
        actor=principal.user_id,
        resource_type="user",
        resource_id=user.id,
        trace_id=getattr(request.state, "trace_id", None),
        detail={"username": user.username, "roles": [r.name for r in roles]},
    )
    return _to_out(user, [r.name for r in roles])


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("user:manage")),
):
    users = (
        await db.execute(select(User).where(User.tenant_id == principal.tenant_id))
    ).scalars().all()
    return [
        _to_out(u, await rbac.load_user_role_names(db, u.id, principal.tenant_id)) for u in users
    ]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("user:manage")),
):
    user = await _load_user(db, user_id, principal)
    return _to_out(user, await rbac.load_user_role_names(db, user.id, principal.tenant_id))


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("user:manage")),
):
    user = await _load_user(db, user_id, principal)

    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise _invalid(f"status must be one of {', '.join(sorted(_VALID_STATUSES))}")
        if body.status != "active" and user.id == principal.user_id:
            # Locking yourself out is unrecoverable without a second administrator or direct
            # database access.
            raise _invalid("you cannot disable your own account")
        user.status = body.status

    if body.roles is not None:
        await _set_roles(db, user.id, await _resolve_roles(db, principal.tenant_id, body.roles))

    await db.commit()
    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="user.update",
        result="allow",
        actor=principal.user_id,
        resource_type="user",
        resource_id=user.id,
        trace_id=getattr(request.state, "trace_id", None),
        detail={"status": body.status, "roles": body.roles},
    )
    return _to_out(user, await rbac.load_user_role_names(db, user.id, principal.tenant_id))


@router.post("/{user_id}/password", response_model=UserOut)
async def reset_password(
    user_id: str,
    body: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: None = Depends(require_permission("user:manage")),
):
    """Administrative reset — no current password required.

    With no email delivery in the system, this is the only recovery path for a forgotten
    password. Use `POST /auth/change-password` to change your own.
    """
    user = await _load_user(db, user_id, principal)
    user.password_hash = hash_password(body.new_password)
    await db.commit()

    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="user.reset_password",
        result="allow",
        actor=principal.user_id,
        resource_type="user",
        resource_id=user.id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    return _to_out(user, await rbac.load_user_role_names(db, user.id, principal.tenant_id))
