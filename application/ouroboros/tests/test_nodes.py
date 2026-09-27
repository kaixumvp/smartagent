"""Unit tests for the core nodes (plan/decide/execute/observe) and their pure helpers."""

import pytest

from conftest import MockLLMGateway, build_default_plugin_registry
from src.core.nodes.decide import run_decide
from src.core.nodes.execute import _coerce_result, run_execute
from src.core.nodes.observe import run_observe
from src.core.nodes.plan import _parse_plan, run_plan
from src.llm.base import LLMResponse, ToolCall, Usage
from src.plugins.base import PluginManifest
from src.plugins.registry import PluginRegistry
from src.ports import PermissionContext, PermissionDecision
from src.skills.prompt_skill import PromptSkill
from src.tools.base import ToolResult


# --------------------------------------------------------------------------- _parse_plan
def test_parse_plan_basic():
    assert _parse_plan('[{"description": "a"}, {"description": "b"}]') == [
        {"id": 1, "description": "a", "status": "pending"},
        {"id": 2, "description": "b", "status": "pending"},
    ]


def test_parse_plan_markdown_fence():
    assert _parse_plan('```json\n[{"description": "a"}]\n```')[0]["description"] == "a"


def test_parse_plan_invalid_json_returns_empty():
    assert _parse_plan("not json") == []


def test_parse_plan_non_list_returns_empty():
    assert _parse_plan('{"description": "a"}') == []


def test_parse_plan_non_dict_items():
    assert _parse_plan('["plain string"]')[0]["description"] == "plain string"


def test_parse_plan_empty_input():
    assert _parse_plan(None) == []
    assert _parse_plan("") == []


# --------------------------------------------------------------------------- _coerce_result
def test_coerce_result_string():
    assert _coerce_result("hi") == "hi"


def test_coerce_result_tool_success():
    assert _coerce_result(ToolResult(success=True, output="ok")) == "ok"


def test_coerce_result_tool_failure():
    assert _coerce_result(ToolResult(success=False, output="", error="bad")) == "Tool execution failed: bad"


def test_coerce_result_dict():
    assert _coerce_result({"a": 1}) == '{"a": 1}'


# --------------------------------------------------------------------------- plan node
@pytest.mark.asyncio
async def test_run_plan_success():
    llm = MockLLMGateway([LLMResponse(content='[{"description": "step1"}, {"description": "step2"}]', usage=Usage())])
    result = await run_plan({"task": "do things", "run_id": "r1"}, llm, "m")
    assert [s["description"] for s in result["plan"]] == ["step1", "step2"]


@pytest.mark.asyncio
async def test_run_plan_falls_back_on_invalid_json():
    llm = MockLLMGateway([LLMResponse(content="not json", usage=Usage())])
    result = await run_plan({"task": "do things"}, llm, "m")
    assert result["plan"] == [{"id": 1, "description": "do things", "status": "pending"}]


@pytest.mark.asyncio
async def test_run_plan_falls_back_when_llm_raises():
    class RaisingLLM:
        async def chat(self, messages, model=None, tools=None):
            raise RuntimeError("boom")

    result = await run_plan({"task": "do things"}, RaisingLLM(), "m")
    assert result["plan"][0]["description"] == "do things"


@pytest.mark.asyncio
async def test_run_plan_injects_memory_context():
    llm = MockLLMGateway([LLMResponse(content='[{"description": "x"}]', usage=Usage())])
    await run_plan({"task": "t", "memory_ctx": [{"content": "偏好简洁"}]}, llm, "m")
    assert "偏好简洁" in llm.calls[0]["messages"][-1]["content"]


# --------------------------------------------------------------------------- decide node
@pytest.mark.asyncio
async def test_run_decide_tool_call():
    llm = MockLLMGateway([LLMResponse(
        tool_calls=[ToolCall(id="c", name="calculator", arguments={"expression": "1+1"})], usage=Usage(),
    )])
    result = await run_decide({"plan": [], "messages": []}, llm, "m", [], None)
    assert result["action"] == "calculator"
    assert result["action_input"] == {"expression": "1+1"}


@pytest.mark.asyncio
async def test_run_decide_finish():
    llm = MockLLMGateway([LLMResponse(content="final answer", usage=Usage())])
    result = await run_decide({"plan": [], "messages": []}, llm, "m", [], None)
    assert result["action"] == "__finish__"
    assert result["result"] == "final answer"


@pytest.mark.asyncio
async def test_run_decide_uses_custom_system_prompt():
    llm = MockLLMGateway([LLMResponse(content="x", usage=Usage())])
    await run_decide({"plan": [], "messages": []}, llm, "m", [], "custom prompt")
    assert llm.calls[0]["messages"][0]["content"] == "custom prompt"


@pytest.mark.asyncio
async def test_run_decide_injects_plan_and_tool_result():
    llm = MockLLMGateway([LLMResponse(content="x", usage=Usage())])
    state = {
        "plan": [{"id": 1, "description": "step"}],
        "messages": [],
        "last_tool_result": "tool output",
    }
    await run_decide(state, llm, "m", [], None)
    contents = [m.get("content", "") for m in llm.calls[0]["messages"]]
    assert any("Current plan" in c for c in contents)
    assert any("Tool result" in c for c in contents)


# --------------------------------------------------------------------------- observe node
@pytest.mark.asyncio
async def test_run_observe_increments_iteration():
    result = await run_observe({"iteration": 0, "messages": [], "max_iterations": 20})
    assert result["iteration"] == 1


@pytest.mark.asyncio
async def test_run_observe_appends_tool_result():
    result = await run_observe({"iteration": 0, "messages": [], "last_tool_result": "out", "max_iterations": 20})
    assert result["messages"] == [{"role": "tool", "content": "out"}]


@pytest.mark.asyncio
async def test_run_observe_hits_cap():
    result = await run_observe({"iteration": 19, "messages": [], "max_iterations": 20})
    assert result["status"] == "completed"
    assert result["result"]


# --------------------------------------------------------------------------- execute node
@pytest.mark.asyncio
async def test_run_execute_success():
    registry = build_default_plugin_registry()
    result = await run_execute({"action": "calculator", "action_input": {"expression": "1+1"}}, registry, None, None)
    assert result["last_tool_result"] == "2"


@pytest.mark.asyncio
async def test_run_execute_noop_on_finish():
    registry = build_default_plugin_registry()
    result = await run_execute({"action": "__finish__"}, registry, None, None)
    assert result["last_tool_result"] is None


@pytest.mark.asyncio
async def test_run_execute_noop_on_empty_action():
    registry = build_default_plugin_registry()
    result = await run_execute({}, registry, None, None)
    assert result["last_tool_result"] is None


class _ApproveChecker:
    def check(self, ctx, action, resource_type, resource_id,
              resource_permission="read", requires_approval=False, approved=None):
        return PermissionDecision.REQUIRE_APPROVAL


@pytest.mark.asyncio
async def test_run_execute_requires_approval():
    registry = build_default_plugin_registry()
    result = await run_execute(
        {"action": "calculator", "action_input": {"expression": "1+1"}},
        registry, _ApproveChecker(), PermissionContext(),
    )
    assert "[approval required]" in result["last_tool_result"]


@pytest.mark.asyncio
async def test_run_execute_injects_memory_ctx_into_prompt_skill():
    registry = PluginRegistry()
    registry.register(PromptSkill(
        PluginManifest(name="p", kind="skill"),
        {"template": "ctx={{memory_ctx}}"},
    ))
    state = {"action": "skill_p", "action_input": {}, "memory_ctx": [{"content": "偏好简洁"}]}
    result = await run_execute(state, registry, None, None)
    assert "偏好简洁" in result["last_tool_result"]
