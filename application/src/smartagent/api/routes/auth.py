from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import write_audit
from smartagent.api.schemas import ChangePasswordRequest, LoginRequest, TokenResponse
from smartagent.api.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from smartagent.config import get_settings
from smartagent.db.models import User
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/auth", tags=["auth"])

_UNKNOWN_TENANT = "unknown"  # audit rows for logins that never resolved to a tenant


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": message})


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    trace_id = getattr(request.state, "trace_id", None)

    stmt = select(User).where(User.username == body.username, User.status == "active")
    if body.tenant:
        stmt = stmt.where(User.tenant_id == body.tenant)
    users = (await db.execute(stmt)).scalars().all()

    if len(users) > 1:
        # `uq_users_tenant_username` makes a username unique *within* a tenant only. Taking the
        # first match would hand the caller an account in a tenant they never named.
        await write_audit(
            db,
            tenant_id=_UNKNOWN_TENANT,
            action="auth.login",
            result="deny",
            actor=body.username,
            trace_id=trace_id,
            detail={"reason": "ambiguous_username"},
        )
        raise _unauthorized("username exists in multiple tenants; specify `tenant`")

    user = users[0] if users else None
    if user is None or not verify_password(body.password, user.password_hash):
        await write_audit(
            db,
            tenant_id=user.tenant_id if user else (body.tenant or _UNKNOWN_TENANT),
            action="auth.login",
            result="deny",
            actor=body.username,
            trace_id=trace_id,
            detail={"reason": "invalid_credentials"},
        )
        raise _unauthorized("invalid credentials")

    settings = get_settings()
    token = create_access_token(user.id, user.tenant_id)
    await write_audit(
        db,
        tenant_id=user.tenant_id,
        action="auth.login",
        result="allow",
        actor=user.id,
        trace_id=trace_id,
    )
    return TokenResponse(access_token=token, token_type="bearer", expires_in=settings.jwt_expire_seconds)


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
):
    """Change your own password. Requires the current one — knowing a valid token is not
    enough, so a stolen token cannot be used to take over the account permanently.

    Administrators reset *someone else's* password via `POST /v1/users/{id}/password`.
    """
    trace_id = getattr(request.state, "trace_id", None)
    user = await db.get(User, principal.user_id)
    if user is None:
        raise _unauthorized("unknown user")

    if not verify_password(body.current_password, user.password_hash):
        await write_audit(
            db,
            tenant_id=principal.tenant_id,
            action="auth.change_password",
            result="deny",
            actor=principal.user_id,
            trace_id=trace_id,
            detail={"reason": "current_password_mismatch"},
        )
        raise _unauthorized("current password is incorrect")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await write_audit(
        db,
        tenant_id=principal.tenant_id,
        action="auth.change_password",
        result="allow",
        actor=principal.user_id,
        trace_id=trace_id,
    )
