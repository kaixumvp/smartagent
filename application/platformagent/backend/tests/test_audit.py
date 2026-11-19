from datetime import datetime, timezone

from fastapi.testclient import TestClient

from conftest import FakeSession, admin_principal, operator_principal
from smartagent.api.security import get_current_user
from smartagent.db.models import AuditLog
from smartagent.db.session import get_db
from smartagent.main import app


def _install(db, principal=None):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: principal or admin_principal()


def test_audit_list_is_tenant_scoped_and_newest_first():
    db = FakeSession(
        AuditLog(
            id="audit_old", tenant_id="default", action="user.create", result="allow",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        AuditLog(
            id="audit_new", tenant_id="default", action="plugin.execute", result="deny",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
        AuditLog(
            id="audit_other", tenant_id="other", action="user.create", result="allow",
            created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
    )
    _install(db)
    try:
        with TestClient(app) as client:
            response = client.get("/v1/audit?limit=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["audit_new"]


def test_audit_list_requires_admin():
    db = FakeSession()
    _install(db, principal=operator_principal())
    try:
        with TestClient(app) as client:
            response = client.get("/v1/audit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
