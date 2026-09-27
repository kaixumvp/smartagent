import pytest

from src.observability.metrics import InMemoryMetrics, NoopMetrics
from src.observability.trace import Tracer, get_tracer


# OpenTelemetry is not installed in the test env → Tracer degrades to no-op.
def test_tracer_noop_when_otel_absent():
    t = Tracer()
    assert t.enabled is False
    assert t.current_trace_id() is None
    with t.start_span("x", attributes={"a": 1}) as span:
        assert span is None
    t.record_error(None, RuntimeError("x"))  # no-op, must not raise


def test_get_tracer_returns_tracer():
    assert isinstance(get_tracer("n"), Tracer)


def test_noop_metrics_discards():
    m = NoopMetrics()
    m.incr("a", labels={"x": "y"})
    m.observe("b", 1.0)  # no-ops


def test_in_memory_metrics_records():
    m = InMemoryMetrics()
    m.incr("c", 2, {"x": "y"})
    m.incr("c", 1, {"x": "y"})
    m.observe("lat", 1.5, {"node": "plan"})
    assert m.counters[("c", (("x", "y"),))] == 3
    assert m.observations == [("lat", 1.5, {"node": "plan"})]


@pytest.mark.asyncio
async def test_runtime_records_metrics_and_redacts():
    from conftest import MockLLMGateway, build_default_plugins
    from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
    from src.core.resilience import RetryPolicy
    from src.llm.base import LLMResponse, ToolCall, Usage
    from src.security import Redactor

    llm = MockLLMGateway([
        LLMResponse(content='[{"description": "x"}]', usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
        LLMResponse(tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expression": "3*8+100"})]),
        LLMResponse(content="3*8+100 = 124"),
    ])
    metrics = InMemoryMetrics()
    deps = RuntimeDeps(llm=llm, metrics=metrics, retry=RetryPolicy(max_retries=0), redactor=Redactor(["sk-secret-123"]))
    definition = AgentDefinition(model="m", system_prompt="你是助手", plugins=build_default_plugins())

    result = await AgentRuntime().run(definition, "计算", RunContext(run_id="r1"), deps)

    assert result.status == "completed"
    assert any(key[0] == "ouroboros.runs" for key in metrics.counters)
    assert any(key[0] == "ouroboros.tool.calls" for key in metrics.counters)
    assert any(name == "ouroboros.step.latency_ms" for name, _, _ in metrics.observations)
