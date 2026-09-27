import pytest

from conftest import MockLLMGateway, build_default_plugin_registry
from src.core.nodes.decide import run_decide
from src.core.nodes.execute import run_execute
from src.core.nodes.observe import run_observe
from src.llm.base import LLMResponse, ToolCall, Usage


@pytest.mark.asyncio
async def test_decide_records_multiple_tool_calls():
    llm = MockLLMGateway([
        LLMResponse(tool_calls=[
            ToolCall(id="c1", name="calculator", arguments={"expression": "1+1"}),
            ToolCall(id="c2", name="calculator", arguments={"expression": "2+2"}),
        ], usage=Usage()),
    ])
    result = await run_decide({"plan": [], "messages": []}, llm, "m", [], None)
    assert result["action"] == "calculator"
    assert result["tool_call_id"] == "c1"
    assert len(result["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_execute_runs_multiple_tool_calls_in_parallel():
    registry = build_default_plugin_registry()
    state = {
        "action": "calculator",
        "tool_calls": [
            {"id": "c1", "name": "calculator", "arguments": {"expression": "1+1"}},
            {"id": "c2", "name": "calculator", "arguments": {"expression": "2+2"}},
        ],
    }
    result = await run_execute(state, registry, None, None)
    assert result["tool_results"] == ["2", "4"]
    assert result["tool_call_ids"] == ["c1", "c2"]
    assert "[calculator] 2" in result["last_tool_result"]
    assert "[calculator] 4" in result["last_tool_result"]


@pytest.mark.asyncio
async def test_observe_appends_multiple_tool_messages():
    state = {
        "iteration": 0,
        "messages": [],
        "max_iterations": 20,
        "tool_results": ["2", "4"],
        "tool_call_ids": ["c1", "c2"],
    }
    result = await run_observe(state)
    assert result["messages"] == [
        {"role": "tool", "content": "2", "tool_call_id": "c1"},
        {"role": "tool", "content": "4", "tool_call_id": "c2"},
    ]
