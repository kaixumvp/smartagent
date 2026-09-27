"""A/B experiments: bucketing, stickiness, and agent version grouping (V1.1)."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from conftest import (
    FakeMemoryManager,
    FakeSession,
    MockLLMGateway,
    admin_permission_context,
    admin_principal,
)
from smartagent.api.deps import get_llm_gateway, get_memory_manager
from smartagent.api.security import get_current_user, get_permission_context
from smartagent.db.models import Agent, AgentExperiment, ExperimentAssignment
from smartagent.db.session import get_db
from smartagent.main import app
from smartagent.services.experiment_service import ExperimentService, pick_variant, subject_key_for
from src.llm.base import LLMResponse, ToolCall, Usage

VARIANTS = [
    {"label": "A", "agent_id": "agent_a", "weight": 90},
    {"label": "B", "agent_id": "agent_b", "weight": 10},
]


def _agent(agent_id: str, name: str = "assistant", version: str = "1", is_latest: bool = True) -> Agent:
    return Agent(
        id=agent_id,
        tenant_id="default",
        name=name,
        version=version,
        config={"model": "test", "tools": ["tool_calculator"]},
        status="active",
        is_latest=is_latest,
    )


# --------------------------------------------------------------------------- bucketing
def test_bucketing_is_deterministic():
    first = [pick_variant("exp_1", f"u{i}", VARIANTS)["label"] for i in range(200)]
    second = [pick_variant("exp_1", f"u{i}", VARIANTS)["label"] for i in range(200)]
    assert first == second


def test_bucketing_respects_weights():
    counts = Counter(pick_variant("exp_1", f"u{i}", VARIANTS)["label"] for i in range(4000))
    # 90/10 split; allow generous slack so the test is not flaky on hash quirks.
    assert 0.86 < counts["A"] / 4000 < 0.94


def test_bucketing_differs_per_experiment():
    """Two experiments must not bucket everyone identically, or a user who lost one test
    would systematically lose every later one."""
    a = [pick_variant("exp_1", f"u{i}", VARIANTS)["label"] for i in range(300)]
    b = [pick_variant("exp_2", f"u{i}", VARIANTS)["label"] for i in range(300)]
    assert a != b


def test_bucketing_handles_zero_weights():
    variants = [{"label": "A", "agent_id": "a", "weight": 0}, {"label": "B", "agent_id": "b", "weight": 0}]
    assert pick_variant("exp", "u1", variants)["label"] in {"A", "B"}


def test_subject_key_prefers_explicit_user():
    assert subject_key_for("u_body", "u_principal", "run_1") == "u_body"
    assert subject_key_for(None, "u_principal", "run_1") == "u_principal"
    # No identity at all → per-run, i.e. not sticky. Deliberate, and worth seeing in results.
    assert subject_key_for(None, None, "run_1") == "run_1"


# --------------------------------------------------------------------------- assignment
@pytest.mark.asyncio
async def test_assignment_is_persisted_and_reused():
    experiment = AgentExperiment(
        id="exp_1", tenant_id="default", name="t", entry_agent_id="agent_entry",
        status="running", variants=VARIANTS, sticky_key="user",
    )
    db = FakeSession(experiment)
    service = ExperimentService(db)

    first = await service.assign(experiment, "u_1")
    second = await service.assign(experiment, "u_1")

    assert first.variant == second.variant
    # Second call read the stored row rather than minting another one.
    assert len(db.rows(ExperimentAssignment)) == 1


@pytest.mark.asyncio
async def test_find_running_ignores_draft_and_other_tenants():
    draft = AgentExperiment(
        id="exp_draft", tenant_id="default", name="d", entry_agent_id="agent_entry",
        status="draft", variants=VARIANTS, sticky_key="user",
    )
    other = AgentExperiment(
        id="exp_other", tenant_id="t2", name="o", entry_agent_id="agent_entry",
        status="running", variants=VARIANTS, sticky_key="user",
    )
    service = ExperimentService(FakeSession(draft, other))

    assert await service.find_running("default", "agent_entry") is None


# --------------------------------------------------------------------------- HTTP
def _install(fake_db, llm):
    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_llm_gateway] = lambda: llm
    app.dependency_overrides[get_memory_manager] = lambda: FakeMemoryManager()
    app.dependency_overrides[get_current_user] = lambda: admin_principal()
    app.dependency_overrides[get_permission_context] = lambda: admin_permission_context()


def _llm() -> MockLLMGateway:
    return MockLLMGateway([
        LLMResponse(content='[{"description": "calc"}]', usage=Usage()),
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "1+1"})],
            usage=Usage(),
        ),
        LLMResponse(content="1+1 = 2", usage=Usage()),
    ])


def test_new_agent_version_becomes_latest():
    db = FakeSession(_agent("agent_v1", version="1"))
    _install(db, _llm())
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/agents", json={"name": "assistant", "version": "2", "config": {}})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 201
    assert resp.json()["is_latest"] is True
    latest = [a for a in db.rows(Agent) if a.is_latest]
    assert len(latest) == 1 and latest[0].version == "2"


def test_duplicate_agent_version_is_rejected():
    db = FakeSession(_agent("agent_v1", version="1"))
    _install(db, _llm())
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/agents", json={"name": "assistant", "version": "1", "config": {}})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"


def test_run_is_routed_to_the_assigned_variant():
    entry = _agent("agent_entry")
    variant_b = _agent("agent_b", name="assistant-b")
    experiment = AgentExperiment(
        id="exp_1", tenant_id="default", name="rollout", entry_agent_id="agent_entry",
        status="running",
        # 100% to B so the assertion does not depend on which bucket the hash picks.
        variants=[{"label": "B", "agent_id": "agent_b", "weight": 100}],
        sticky_key="user",
    )
    db = FakeSession(entry, variant_b, experiment)
    _install(db, _llm())

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/v1/agents/agent_entry/runs", json={"input": "1+1", "user_id": "u_1"}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "agent_b"  # served by the variant, not the entry agent
    run = db.runs[0]
    assert (run.experiment_id, run.variant) == ("exp_1", "B")


def test_run_without_experiment_is_untouched():
    db = FakeSession(_agent("agent_entry"))
    _install(db, _llm())
    try:
        with TestClient(app) as client:
            resp = client.post("/v1/agents/agent_entry/runs", json={"input": "1+1", "user_id": "u_1"})
    finally:
        app.dependency_overrides.clear()

    assert resp.json()["agent_id"] == "agent_entry"
    assert db.runs[0].experiment_id is None
