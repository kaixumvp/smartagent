from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.api.schemas import AuditLogOut
from smartagent.api.security import get_current_user, require_admin
from smartagent.db.models import AuditLog
from smartagent.db.session import get_db
from smartagent.iam.permission_manager import Principal

router = APIRouter(prefix="/audit", tags=["iam"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_user),
    _: Principal = Depends(require_admin),
):
    rows = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == principal.tenant_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        AuditLogOut(
            id=row.id,
            tenant_id=row.tenant_id,
            trace_id=row.trace_id,
            actor=row.actor,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            result=row.result,
            detail=row.detail,
            created_at=row.created_at,
        )
        for row in rows
    ]
