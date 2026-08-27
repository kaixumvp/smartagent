"""JWT issuance/verification, password hashing, and the authenticated-principal dependency.

Auth is implemented as a FastAPI dependency (rather than middleware) because it needs to return
structured 401/403 errors and vary per-route; tenant injection derives from the authenticated
principal. When `auth_enabled` is false (dev/test), a default admin principal is returned.
"""

import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.adapters.audit import write_audit
from smartagent.api.deps import get_permission_manager
from smartagent.config import get_settings
from smartagent.db.models import User
from smartagent.db.session import get_db
from smartagent.iam import rbac
from smartagent.iam.permission_manager import PermissionContext, Principal

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt (self-describing string)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verification of a PBKDF2 hash produced by hash_password."""
    try:
        _, iters, salt_b64, dk_b64 = hashed.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
    return hmac.compare_digest(dk, expected)


def create_access_token(user_id: str, tenant_id: str, expires_seconds: int | None = None) -> str:
    """Issue a JWT carrying identity (roles are NOT embedded; they are resolved per request)."""
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds or settings.jwt_expire_seconds)
    payload = {"sub": user_id, "tenant_id": tenant_id, "scope": "api", "exp": expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT; raises jwt.PyJWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": message})


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    """Resolve the authenticated principal from the Authorization header."""
    settings = get_settings()
    if not settings.auth_enabled:
        return Principal(user_id="system", tenant_id="default", roles=["admin"], is_admin=True)

    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise _unauthorized("missing bearer token")
    try:
        payload = decode_token(auth[7:])
    except jwt.PyJWTError:
        raise _unauthorized("invalid or expired token")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id", "default")
    if not user_id:
        raise _unauthorized("malformed token")

    user = await db.get(User, user_id)
    if user is None or user.tenant_id != tenant_id or user.status != "active":
        raise _unauthorized("unknown or disabled user")

    role_names = await rbac.load_user_role_names(db, user_id, tenant_id)
    return Principal(user_id=user_id, tenant_id=tenant_id, roles=role_names, is_admin="admin" in role_names)


async def get_permission_context(
    principal: Principal = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PermissionContext:
    """Build the authorization snapshot for the current principal."""
    return await get_permission_manager().build_context(db, principal)


def require_permission(code: str) -> Callable:
    """Dependency factory: require a functional permission code (or admin)."""

    async def _dep(
        request: Request,
        ctx: PermissionContext = Depends(get_permission_context),
        principal: Principal = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> PermissionContext:
        if ctx.is_admin or code in ctx.permission_codes:
            return ctx
        # A refused call is exactly what the audit trail is for (V0.2实施规格 §7.2).
        await write_audit(
            db,
            tenant_id=principal.tenant_id,
            action="permission.check",
            result="deny",
            actor=principal.user_id,
            trace_id=getattr(request.state, "trace_id", None),
            detail={"required": code, "path": request.url.path},
        )
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": f"missing permission: {code}"},
        )

    return _dep


def require_admin(principal: Principal = Depends(get_current_user)) -> Principal:
    """Dependency: require the admin role."""
    if principal.is_admin:
        return principal
    raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "admin role required"})
