"""Audit trail (business adapter): who did what, and how the decision came out.

Backs the `audit_logs` table created in Alembic 0002. Every writer here is best-effort —
auditing must never break the request it is recording.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from smartagent.db.models import AuditLog
from smartagent.util import new_id
from ouroboros.ports import PermissionContext, PermissionDecision

logger = logging.getLogger(__name__)


async def write_audit(
    db: AsyncSession,
    *,
    tenant_id: str,
    action: str,
    result: str,
    actor: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    trace_id: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append one audit row. Swallows its own failures (and rolls back) by design."""
    try:
        db.add(
            AuditLog(
                id=new_id("audit"),
                tenant_id=tenant_id,
                trace_id=trace_id,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result=result,
                detail=detail,
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — an audit failure must not surface as a request failure
        logger.exception("audit write failed: action=%s tenant=%s", action, tenant_id)
        await db.rollback()


class AuditingPermissionChecker:
    """Wraps a `PermissionChecker`, buffering every non-ALLOW decision for a later flush.

    The framework's execute node calls `check()` synchronously and has no database handle or
    tenant context, and `get_permission_manager()` is an `@lru_cache` process-wide singleton
    that cannot hold per-request state. Buffering on a short-lived wrapper is what lets a
    denied tool call still leave a trace (V0.2实施规格 §7.2 / §702).
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.decisions: list[dict] = []

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
        decision = self._inner.check(
            ctx,
            action,
            resource_type,
            resource_id,
            resource_permission=resource_permission,
            requires_approval=requires_approval,
            approved=approved,
        )
        if decision is not PermissionDecision.ALLOW:
            self.decisions.append(
                {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "action": action,
                    "decision": decision.value,
                    "resource_permission": resource_permission,
                }
            )
        return decision


async def flush_permission_decisions(
    db: AsyncSession,
    checker: AuditingPermissionChecker,
    *,
    tenant_id: str,
    actor: str | None,
    run_id: str,
    trace_id: str | None = None,
) -> None:
    """Persist the buffered deny / require_approval decisions of one run."""
    for entry in checker.decisions:
        await write_audit(
            db,
            tenant_id=tenant_id,
            action="plugin.execute",
            result=entry["decision"],
            actor=actor,
            resource_type=entry["resource_type"],
            resource_id=entry["resource_id"],
            trace_id=trace_id,
            detail={"run_id": run_id, "resource_permission": entry["resource_permission"]},
        )
    checker.decisions.clear()
