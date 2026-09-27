"""RBAC helpers: resolve a user's roles and the effective permission codes they grant."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import Permission, Role, RolePermission, UserRole


async def load_user_role_ids(db: AsyncSession, user_id: str, tenant_id: str) -> list[str]:
    rows = (
        await db.execute(
            select(Role.id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.tenant_id == tenant_id)
        )
    ).scalars().all()
    return list(rows)


async def load_user_role_names(db: AsyncSession, user_id: str, tenant_id: str) -> list[str]:
    rows = (
        await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Role.tenant_id == tenant_id)
        )
    ).scalars().all()
    return list(rows)


async def load_permission_codes(db: AsyncSession, role_ids: list[str]) -> set[str]:
    """Permission codes reachable through the given roles."""
    if not role_ids:
        return set()
    rows = (
        await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(role_ids))
        )
    ).scalars().all()
    return set(rows)
