"""Resolve user and role resource grants in the current tenant."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import Grant


async def load_grants(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    role_ids: list[str],
) -> list[Grant]:
    """Return grants for the user and their roles without discarding action semantics."""
    user_clause = and_(Grant.principal_type == "user", Grant.principal_id == user_id)
    role_clause = and_(Grant.principal_type == "role", Grant.principal_id.in_(role_ids))
    if role_ids:
        predicate = or_(user_clause, role_clause)
    else:
        predicate = user_clause

    return list((
        await db.execute(select(Grant).where(Grant.tenant_id == tenant_id, predicate))
    ).scalars().all())
