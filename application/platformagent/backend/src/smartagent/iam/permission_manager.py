"""Business-side permission manager: loads RBAC/Grant data into a PermissionContext.

The pure decision logic (check_permission) lives in the framework (ouroboros.ports);
this module only resolves data (build_context) and exposes a thin check() for the runtime.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.iam import grants as grants_mod
from smartagent.iam import rbac
from src.ports import (
    PermissionContext,
    PermissionDecision,
    Principal,
    check_permission,
)


class PermissionManager:
    """Resolves a Principal into a PermissionContext and evaluates checks against it."""

    async def build_context(self, db: AsyncSession, principal: Principal) -> PermissionContext:
        role_ids = await rbac.load_user_role_ids(db, principal.user_id, principal.tenant_id)
        role_names = await rbac.load_user_role_names(db, principal.user_id, principal.tenant_id)
        permission_codes = await rbac.load_permission_codes(db, role_ids)
        grant_keys = await grants_mod.load_grant_keys(db, principal.tenant_id, principal.user_id, role_ids)
        return PermissionContext(
            permission_codes=permission_codes,
            grant_keys=grant_keys,
            is_admin="admin" in role_names,
        )

    def check(
        self,
        ctx: PermissionContext,
        action: str,
        resource_type: str,
        resource_id: str,
        resource_permission: str = "read",
        requires_approval: bool = False,
        approved: set[str] | None = None,
    ) -> PermissionDecision:
        return check_permission(
            ctx,
            action,
            resource_type,
            resource_id,
            resource_permission=resource_permission,
            requires_approval=requires_approval,
            approved=approved,
        )
