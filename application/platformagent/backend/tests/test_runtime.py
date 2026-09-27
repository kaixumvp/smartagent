"""Business-side runtime assembly and event recording.

The agent loop itself belongs to the framework and is covered by ouroboros' own
`tests/test_runtime_facade.py`. What matters here is the business layer's half of the
contract: a persisted Agent row plus `Settings` must turn into the right
`AgentDefinition`/`RuntimeConfig`, and the framework's events must land in the database.
"""

import asyncio

import pytest

from conftest import (
    FakeMemoryManager,
    FakeSession,
    MockLLMGateway,
    admin_permission_context,
    admin_principal,
)
from smartagent.adapters.run_recorder import RunRecorder
from smartagent.config import Settings
from smartagent.db.models import Agent, Run
from smartagent.iam.permission_manager import PermissionManager
from smartagent.services.run_service import RunService
from src.events.events import run_awaiting_human, run_completed, step_completed
from src.plugins.registry import PluginRegistry
from src.tools.registry import build_default_registry


def _service(db=None, settings: Settings | None = None) -> RunService:
    return RunService(
        db=db or FakeSession(),
        llm=MockLLMGateway([]),
        memory=FakeMemoryManager(),
        settings=settings or Settings(),
        principal=admin_principal(),
        permission_context=admin_permission_context(),
        permission_manager=PermissionManager(),
        tool_registry=build_default_registry(),
    )


def _agent(config: dict) -> Agent:
    return Agent(
        id="agent_test", tenant_id="default", name="t", version="1", config=config, status="active"
    )


def _run() -> Run:
    return Run(id="run_1", agent_id="agent_test", tenant_id="default", input="x", status="running")


# --------------------------------------------------------------------------- assembly
def test_runtime_config_falls_back_to_settings():
    settings = Settings(max_iterations=7, timeout_seconds=33, max_subagent_depth=2)
    config = _service(settings=settings).build_runtime_config({})

    assert config.max_iterations == 7
    assert config.timeout_seconds == 33.0
    assert config.max_subagent_depth == 2
    assert config.max_total_tokens == 0  # unlimited unless the agent opts in


def test_runtime_config_agent_overrides_settings():
    settings = Settings(max_iterations=7, max_subagent_depth=2)
    config = _service(settings=settings).build_runtime_config(
        {"runtime": {"max_iterations": 3, "max_total_tokens": 500}}
    )

    assert config.max_iterations == 3
    assert config.max_total_tokens == 500
    assert config.max_subagent_depth == 2  # untouched keys still come from Settings


def test_definition_prefers_agent_model():
    """Regression guard: V0.2 had two call sites passing different things as the model —
    one a `Settings` object, one `settings.llm_model` — and neither honoured `config.model`."""
    service = _service(settings=Settings(llm_model="settings-model"))

    definition = service.build_definition(
        _agent({"model": "agent-model", "system_prompt": "you are a test"}), PluginRegistry()
    )

    assert definition.model == "agent-model"
    assert definition.system_prompt == "you are a test"
    assert definition.agent_id == "agent_test"


def test_definition_leaves_model_empty_when_agent_pins_none():
    """V1.1 moved the model fallback out of here and into the per-run gateway.

    Resolving to `settings.llm_model` at this point would make every model concrete, and since
    the runtime forwards `definition.model` to every node (runtime.py:249), tiered routing
    could never engage. An empty model is the signal that the agent pinned none.
    """
    service = _service(settings=Settings(llm_model="settings-model"))
    assert service.build_definition(_agent({}), PluginRegistry()).model == ""


# --------------------------------------------------------------------------- event recording
@pytest.mark.asyncio
async def test_run_recorder_persists_steps_and_completion():
    db = FakeSession()
    run = _run()
    db.add(run)
    recorder = RunRecorder(db, run.id)

    await recorder(
        step_completed(
            {"seq": 1, "node": "plan", "action": None, "output": {"plan": []},
             "latency_ms": 5, "run_id": run.id}
        )
    )
    await recorder(run_completed(run.id, "done", {"total_tokens": 9}))

    assert [s.node for s in db.steps] == ["plan"]
    assert db.steps[0].status == "success"
    assert (run.status, run.result) == ("completed", "done")
    assert run.token_usage["total_tokens"] == 9
    assert run.finished_at is not None
    assert run.pending_approvals is None


@pytest.mark.asyncio
async def test_run_recorder_marks_paused_step_awaiting_human():
    """`step.completed` carries no status field, so the recorder has to correct the blocked
    step when the pause event arrives right behind it."""
    db = FakeSession()
    run = _run()
    db.add(run)
    recorder = RunRecorder(db, run.id)
    pending = [{"resource_type": "tool", "resource_id": "delete_account", "action": "delete_account"}]

    await recorder(
        step_completed(
            {"seq": 1, "node": "execute", "action": "delete_account", "output": {},
             "latency_ms": 1, "run_id": run.id}
        )
    )
    await recorder(run_awaiting_human(run.id, pending))

    assert db.steps[-1].status == "awaiting_human"
    assert run.status == "awaiting_human"
    assert run.pending_approvals == pending
    assert run.finished_at is None  # paused, not finished


@pytest.mark.asyncio
async def test_run_recorder_fans_out_to_queue():
    db = FakeSession()
    run = _run()
    db.add(run)
    queue: asyncio.Queue = asyncio.Queue()
    recorder = RunRecorder(db, run.id, queue=queue)

    await recorder(run_completed(run.id, "done", {}))

    assert queue.get_nowait().event == "run.completed"
