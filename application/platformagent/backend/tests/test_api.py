"""HTTP-level acceptance for V0.2: a run must work across
{high-risk tool present, absent} × {sync, SSE}, and an approval must continue the same run.
"""

from fastapi.testclient import TestClient

from conftest import (
    FakeMemoryManager,
    FakeSession,
    MockLLMGateway,
    admin_permission_context,
    admin_principal,
    high_risk_tool_registry,
    operator_permission_context,
    operator_principal,
)
from smartagent.api.deps import get_llm_gateway, get_memory_manager, get_tool_registry
from smartagent.api.security import get_current_user, get_permission_context
from smartagent.db.models import Agent
from smartagent.db.session import get_db
from smartagent.main import app
from src.llm.base import LLMResponse, ToolCall, Usage


def _plan_response() -> LLMResponse:
    return LLMResponse(content='[{"description": "Calculate 3*8+100"}]', usage=Usage())


def _calc_call_response() -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "3*8+100"})],
        usage=Usage(),
    )


def _finish_response() -> LLMResponse:
    return LLMResponse(content="3*8+100 = 124", usage=Usage())


def _delete_call_response() -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="delete_account", arguments={"user_id": "u42"})],
        usage=Usage(),
    )


def _calc_agent() -> Agent:
    return Agent(
        id="agent_test",
        tenant_id="default",
        name="Test Agent",
        version="1",
        config={"model": "test", "tools": ["tool_calculator"], "system_prompt": "assistant"},
        status="active",
    )


def _high_risk_agent() -> Agent:
    return Agent(
        id="agent_test",
        tenant_id="default",
        name="Ops Agent",
        version="1",
        config={"model": "test", "tools": ["delete_account"], "system_prompt": "ops"},
        status="active",
    )


def _install_overrides(fake_db, llm, memory, *, principal=None, perm_ctx=None, tool_registry=None):
    async def override_db():
        yield fake_db

    async def override_llm():
        return llm

    async def override_memory():
        return memory

    async def override_user():
        return principal or admin_principal()

    async def override_perm_ctx():
        return perm_ctx or admin_permission_context()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm_gateway] = override_llm
    app.dependency_overrides[get_memory_manager] = override_memory
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_permission_context] = override_perm_ctx
    if tool_registry is not None:
        app.dependency_overrides[get_tool_registry] = lambda: tool_registry


def _sse_events(body: str) -> list[str]:
    return [line[len("event: "):] for line in body.splitlines() if line.startswith("event: ")]


def test_health():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_run_invalid_input():
    fake_db = FakeSession(_calc_agent())
    _install_overrides(fake_db, MockLLMGateway([]), FakeMemoryManager())
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/agents/agent_test/runs", json={"input": ""})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_ARGUMENT"


# --------------------------------------------------------------- no high-risk tool
def test_create_run_end_to_end():
    llm = MockLLMGateway([_plan_response(), _calc_call_response(), _finish_response()])
    fake_db = FakeSession(_calc_agent())
    _install_overrides(fake_db, llm, FakeMemoryManager())

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "Calculate 3*8 then add 100", "stream": False, "user_id": "u_1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["run_id"].startswith("run_")
    assert "124" in (data["result"] or "")
    assert len(data["steps"]) >= 4


def test_create_run_stream_emits_event_sequence():
    llm = MockLLMGateway([_plan_response(), _calc_call_response(), _finish_response()])
    fake_db = FakeSession(_calc_agent())
    _install_overrides(fake_db, llm, FakeMemoryManager())

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "Calculate 3*8 then add 100", "stream": True, "user_id": "u_1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(resp.text)
    assert events[0] == "run.started"
    assert events[-1] == "run.completed"
    assert "step.completed" in events
    # The stream is the only path that wrote steps — they still had to land in the database.
    assert len(fake_db.steps) >= 4


# --------------------------------------------------------------- high-risk tool (HITL)
def test_create_run_pauses_on_high_risk_tool():
    llm = MockLLMGateway([_plan_response(), _delete_call_response()])
    fake_db = FakeSession(_high_risk_agent())
    _install_overrides(
        fake_db,
        llm,
        FakeMemoryManager(),
        principal=operator_principal(),
        perm_ctx=operator_permission_context({("tool", "delete_account")}),
        tool_registry=high_risk_tool_registry(),
    )

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "delete account u42", "stream": False, "user_id": "u_op"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "awaiting_human"
    assert data["pending_approvals"] == [{"resource_type": "tool", "resource_id": "delete_account"}]
    assert data["result"] is None
    # A checkpoint must exist, or the approval below has nothing to resume from.
    assert fake_db.runs[0].checkpoint is not None


def test_create_run_stream_pauses_on_high_risk_tool():
    llm = MockLLMGateway([_plan_response(), _delete_call_response()])
    fake_db = FakeSession(_high_risk_agent())
    _install_overrides(
        fake_db,
        llm,
        FakeMemoryManager(),
        principal=operator_principal(),
        perm_ctx=operator_permission_context({("tool", "delete_account")}),
        tool_registry=high_risk_tool_registry(),
    )

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "delete account u42", "stream": True, "user_id": "u_op"},
            )
    finally:
        app.dependency_overrides.clear()

    events = _sse_events(resp.text)
    assert events[0] == "run.started"
    assert events[-1] == "run.awaiting_human"


def test_approve_resumes_the_same_run():
    """The whole point of mid-run HITL: approving continues the paused run instead of
    replaying it, so plan/decide are not re-executed."""
    llm = MockLLMGateway([_plan_response(), _delete_call_response(), _finish_response()])
    fake_db = FakeSession(_high_risk_agent())
    _install_overrides(
        fake_db,
        llm,
        FakeMemoryManager(),
        principal=operator_principal(),
        perm_ctx=operator_permission_context({("tool", "delete_account")}),
        tool_registry=high_risk_tool_registry(),
    )

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "delete account u42", "stream": False, "user_id": "u_op"},
            ).json()
            assert created["status"] == "awaiting_human"
            paused_steps = len(created["steps"])

            resumed = client.post(
                f"/v1/runs/{created['run_id']}/actions", json={"action": "approve"}
            ).json()
    finally:
        app.dependency_overrides.clear()

    assert resumed["run_id"] == created["run_id"]  # same run, not a replay
    assert resumed["status"] == "completed"
    assert resumed["pending_approvals"] == []
    assert len(resumed["steps"]) > paused_steps
    # plan ran once across both requests; a replay would have produced a second one.
    assert [s["node"] for s in resumed["steps"]].count("plan") == 1
    assert fake_db.runs[0].approvals == ["delete_account"]
    assert "run.approve" in fake_db.audit_actions()

    # The framework restarts its step counter on resume; `seq` is the run's whole timeline,
    # so the resumed half must continue numbering rather than collide with 1..N.
    seqs = [s["seq"] for s in resumed["steps"]]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    assert [s["node"] for s in resumed["steps"]] == [
        "plan", "decide", "execute", "execute", "observe", "decide"
    ]


def test_reject_cancels_run():
    llm = MockLLMGateway([_plan_response(), _delete_call_response()])
    fake_db = FakeSession(_high_risk_agent())
    _install_overrides(
        fake_db,
        llm,
        FakeMemoryManager(),
        principal=operator_principal(),
        perm_ctx=operator_permission_context({("tool", "delete_account")}),
        tool_registry=high_risk_tool_registry(),
    )

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "delete account u42", "stream": False, "user_id": "u_op"},
            ).json()
            rejected = client.post(
                f"/v1/runs/{created['run_id']}/actions", json={"action": "reject"}
            ).json()
    finally:
        app.dependency_overrides.clear()

    assert rejected["status"] == "canceled"
    assert rejected["pending_approvals"] == []
    assert "run.reject" in fake_db.audit_actions()


def test_action_on_running_run_is_rejected():
    llm = MockLLMGateway([_plan_response(), _calc_call_response(), _finish_response()])
    fake_db = FakeSession(_calc_agent())
    _install_overrides(fake_db, llm, FakeMemoryManager())

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/agents/agent_test/runs",
                json={"input": "Calculate 3*8 then add 100", "user_id": "u_1"},
            ).json()
            resp = client.post(f"/v1/runs/{created['run_id']}/actions", json={"action": "approve"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"
