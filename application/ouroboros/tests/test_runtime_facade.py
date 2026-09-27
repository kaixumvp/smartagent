import asyncio

import pytest

from conftest import MockLLMGateway, build_default_plugins
from src.core.checkpointer import InMemoryCheckpointer
from src.core.nodes.execute import run_execute
from src.core.resilience import RetryPolicy
from src.core.runtime import (
    AgentDefinition,
    AgentRuntime,
    RunContext,
    RuntimeConfig,
    RuntimeDeps,
)
from src.llm.base import LLMResponse, ToolCall, Usage
from src.plugins.registry import PluginRegistry
from src.ports import PluginManifest, PermissionContext, PermissionDecision
from src.skills.agent_skill import AgentSkill


def _plan_response() -> LLMResponse:
    return LLMResponse(
        content='[{"description": "Calculate 3*8+100"}]',
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _calc_call_response() -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "3*8+100"})],
        usage=Usage(),
    )


def _finish_response() -> LLMResponse:
    return LLMResponse(content="3*8+100 = 124", usage=Usage())


def _definition(**overrides) -> AgentDefinition:
    kwargs = {"model": "test-model", "plugins": build_default_plugins(), "system_prompt": "你是助手"}
    kwargs.update(overrides)
    return AgentDefinition(**kwargs)


@pytest.mark.asyncio
async def test_runtime_converges_with_tool_call():
    llm = MockLLMGateway([_plan_response(), _calc_call_response(), _finish_response()])
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=0))
    rt = AgentRuntime()

    res = await rt.run(_definition(), "计算 3*8 再加 100", RunContext(run_id="r1"), deps)

    assert res.status == "completed"
    assert "124" in (res.result or "")
    assert res.token_usage["prompt_tokens"] == 10
    assert any(s.node == "execute" for s in res.steps)
    assert [s.node for s in res.steps] == ["plan", "decide", "execute", "observe", "decide"]


@pytest.mark.asyncio
async def test_runtime_retries_transient_plugin_failure():
    class FlakyPlugin:
        kind = "tool"

        def __init__(self) -> None:
            self.calls = 0

        @property
        def manifest(self):
            return PluginManifest(name="flaky", kind="tool")

        async def setup(self, config):
            return None

        async def teardown(self):
            return None

        async def invoke(self, ctx, **kw):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("transient")
            return "recovered"

    flaky = FlakyPlugin()
    llm = MockLLMGateway([
        _plan_response(),
        LLMResponse(tool_calls=[ToolCall(id="c1", name="flaky", arguments={})], usage=Usage()),
        _finish_response(),
    ])
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=3, base_delay=0))
    rt = AgentRuntime()

    res = await rt.run(_definition(plugins=[flaky]), "do it", RunContext(run_id="r1"), deps)

    assert res.status == "completed"
    assert flaky.calls == 3


@pytest.mark.asyncio
async def test_runtime_times_out():
    class SlowLLM:
        async def chat(self, messages, model=None, tools=None):
            await asyncio.sleep(0.2)
            return LLMResponse(content="", usage=Usage())

    deps = RuntimeDeps(llm=SlowLLM(), retry=RetryPolicy(max_retries=0))
    rt = AgentRuntime()
    definition = _definition(runtime=RuntimeConfig(timeout_seconds=0.05))

    res = await rt.run(definition, "slow task", RunContext(run_id="r1"), deps)

    assert res.status == "failed"
    assert "timed out" in (res.error or "")


@pytest.mark.asyncio
async def test_runtime_pauses_for_approval_and_resumes():
    class ApprovalChecker:
        def check(self, ctx, action, resource_type, resource_id,
                  resource_permission="read", requires_approval=False, approved=None):
            if resource_id == "calculator" and "calculator" not in (approved or set()):
                return PermissionDecision.REQUIRE_APPROVAL
            return PermissionDecision.ALLOW

    llm = MockLLMGateway([_plan_response(), _calc_call_response(), _finish_response()])
    checkpointer = InMemoryCheckpointer()
    deps = RuntimeDeps(
        llm=llm,
        permission_checker=ApprovalChecker(),
        permission_context=PermissionContext(permission_codes={"run:execute"}),
        checkpointer=checkpointer,
        retry=RetryPolicy(max_retries=0),
    )
    rt = AgentRuntime()

    paused = await rt.run(_definition(), "计算 3*8 再加 100", RunContext(run_id="r1"), deps)
    assert paused.status == "awaiting_human"
    assert paused.pending_approvals[0]["resource_id"] == "calculator"

    resumed = await rt.resume(_definition(), "r1", ["calculator"], deps)
    assert resumed.status == "completed"
    assert "124" in (resumed.result or "")


@pytest.mark.asyncio
async def test_execute_refuses_deep_subagent():
    registry = PluginRegistry()
    registry.register(AgentSkill(PluginManifest(name="escalate", kind="skill"), {"agent_ref": "a"}))

    state = {"action": "escalate", "action_input": {}, "subagent_depth": 3, "max_subagent_depth": 3}
    result = await run_execute(state, registry, None, None)

    assert "[refused]" in result["last_tool_result"]
