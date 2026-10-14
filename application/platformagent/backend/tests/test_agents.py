from fastapi.testclient import TestClient

from conftest import FakeSession, admin_permission_context, admin_principal
from smartagent.api.security import get_current_user, get_permission_context
from smartagent.db.models import Agent
from smartagent.db.session import get_db
from smartagent.main import app


def _install(db: FakeSession) -> None:
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin_principal()
    app.dependency_overrides[get_permission_context] = lambda: admin_permission_context()


def _agent(agent_id: str, version: str, *, latest: bool = False) -> Agent:
    return Agent(
        id=agent_id,
        tenant_id="default",
        name="Assistant",
        version=version,
        config={"plugins": [{"type": "tool", "ref": "tool:calculator"}]},
        status="active",
        is_latest=latest,
    )


def test_update_agent_config_unbinds_plugin():
    agent = _agent("agent_current", "2", latest=True)
    db = FakeSession(agent)
    _install(db)
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/v1/agents/agent_current",
                json={"config": {"plugins": [], "model": "test-model"}},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["config"] == {"plugins": [], "model": "test-model"}
    assert agent.config == {"plugins": [], "model": "test-model"}


def test_delete_agent_soft_deletes_and_promotes_previous_version():
    previous = _agent("agent_v1", "1")
    latest = _agent("agent_v2", "2", latest=True)
    db = FakeSession(previous, latest)
    _install(db)
    try:
        with TestClient(app) as client:
            response = client.delete("/v1/agents/agent_v2")
            listed = client.get("/v1/agents")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert latest.status == "deleted"
    assert latest.is_latest is False
    assert previous.is_latest is True
    assert [item["id"] for item in listed.json()] == ["agent_v1"]


def test_delete_agent_does_not_expose_other_tenant_agent():
    other_tenant = _agent("agent_other", "1", latest=True)
    other_tenant.tenant_id = "tenant_other"
    db = FakeSession(other_tenant)
    _install(db)
    try:
        with TestClient(app) as client:
            response = client.delete("/v1/agents/agent_other")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert other_tenant.status == "active"
