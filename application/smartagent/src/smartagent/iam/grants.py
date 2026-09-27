"""Resource-level grants: resolve which (resource_type, resource_id, effect) triples apply
to a user through their own grants and the grants of the roles they hold."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import Grant


async def load_grant_keys(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    role_ids: list[str],
) -> set[tuple[str, str, str]]:
    """Return {(resource_type, resource_id, effect)} for the user and their roles."""
    user_clause = and_(Grant.principal_type == "user", Grant.principal_id == user_id)
    role_clause = and_(Grant.principal_type == "role", Grant.principal_id.in_(role_ids))
    if role_ids:
        predicate = or_(user_clause, role_clause)
    else:
        predicate = user_clause

    rows = (
        await db.execute(select(Grant).where(Grant.tenant_id == tenant_id, predicate))
    ).scalars().all()
    return {(g.resource_type, g.resource_id, g.effect) for g in rows}
