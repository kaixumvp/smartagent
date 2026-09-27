import pytest

from conftest import MockLLMGateway, build_default_plugin_registry
from src import AgentDefinition, AgentRuntime, RunContext, RuntimeConfig, RuntimeDeps
from src.core.nodes.execute import run_execute
from src.core.resilience import RetryPolicy
from src.llm.base import LLMResponse, ToolCall, Usage
from src.ports import PermissionContext, PermissionDecision


def _calc_call_response() -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "1+1"})],
        usage=Usage(),
    )


@pytest.mark.asyncio
async def test_runtime_stops_at_max_iterations():
    # Always requests the tool and never finishes — verify the iteration cap fallback, no infinite loop
    llm = MockLLMGateway([_calc_call_response()] * 30)
    definition = AgentDefinition(
        model="test-model",
        system_prompt="你是助手",
        plugins=build_default_plugin_registry().all(),
        runtime=RuntimeConfig(max_iterations=3),
    )
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=0))

    result = await AgentRuntime().run(definition, "计算", RunContext(run_id="r1"), deps)

    assert result.status == "completed"
    assert result.steps[-1].node == "observe"


class _DenyChecker:
    def check(self, ctx, action, resource_type, resource_id,
              resource_permission="read", requires_approval=False, approved=None):
        return PermissionDecision.DENY


@pytest.mark.asyncio
async def test_execute_denies_without_permission():
    registry = build_default_plugin_registry()
    state = {"action": "calculator", "action_input": {"expression": "1+1"}}

    result = await run_execute(state, registry, _DenyChecker(), PermissionContext())
    assert "[denied]" in result["last_tool_result"]


@pytest.mark.asyncio
async def test_execute_unknown_plugin():
    registry = build_default_plugin_registry()
    state = {"action": "does_not_exist", "action_input": {}}

    result = await run_execute(state, registry, None, None)
    assert "unknown plugin" in result["last_tool_result"]
