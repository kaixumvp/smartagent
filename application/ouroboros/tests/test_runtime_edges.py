import pytest

from conftest import FakeKnowledge, FakeLongTermMemory, MockLLMGateway, build_default_plugins
from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.core.checkpointer import InMemoryCheckpointer
from src.core.nodes.execute import run_execute
from src.core.resilience import CircuitBreaker, RetryPolicy
from src.llm.base import LLMResponse, ToolCall, Usage
from src.plugins.registry import PluginRegistry
from src.ports import KnowledgeEntry, PluginManifest


def _def(**overrides) -> AgentDefinition:
    kw = {"model": "m", "system_prompt": "s", "plugins": build_default_plugins()}
    kw.update(overrides)
    return AgentDefinition(**kw)


@pytest.mark.asyncio
async def test_resume_requires_checkpointer():
    rt = AgentRuntime()
    deps = RuntimeDeps(llm=MockLLMGateway())
    with pytest.raises(RuntimeError, match="checkpointer"):
        await rt.resume(_def(), "r1", [], deps)


@pytest.mark.asyncio
async def test_resume_unknown_run_raises():
    rt = AgentRuntime()
    deps = RuntimeDeps(llm=MockLLMGateway(), checkpointer=InMemoryCheckpointer())
    with pytest.raises(RuntimeError, match="no checkpoint"):
        await rt.resume(_def(), "unknown", [], deps)


@pytest.mark.asyncio
async def test_custom_id_generator():
    llm = MockLLMGateway([
        LLMResponse(content='[{"description": "x"}]', usage=Usage()),
        LLMResponse(content="done", usage=Usage()),
    ])
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=0), id_gen=lambda prefix: f"{prefix}_custom")

    result = await AgentRuntime().run(_def(), "hi", RunContext(), deps)

    assert result.steps[0].run_id == "run_custom"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_and_fails_run():
    class AlwaysFails:
        kind = "tool"

        @property
        def manifest(self):
            return PluginManifest(name="f", kind="tool")

        async def setup(self, c):
            pass

        async def teardown(self):
            pass

        async def invoke(self, ctx, **kw):
            raise RuntimeError("boom")

    llm = MockLLMGateway([
        LLMResponse(content='[{"description": "x"}]', usage=Usage()),
        LLMResponse(tool_calls=[ToolCall(id="c1", name="f", arguments={})], usage=Usage()),
    ])
    deps = RuntimeDeps(
        llm=llm,
        retry=RetryPolicy(max_retries=2, base_delay=0),
        circuit_breaker=CircuitBreaker(failure_threshold=1),
    )

    result = await AgentRuntime().run(_def(plugins=[AlwaysFails()]), "do", RunContext(run_id="r1"), deps)

    assert result.status == "failed"
    assert "circuit breaker open" in (result.error or "")


@pytest.mark.asyncio
async def test_execute_propagates_trace_id_to_invoke_context():
    captured = {}

    class CapturingPlugin:
        kind = "tool"

        @property
        def manifest(self):
            return PluginManifest(name="cap", kind="tool")

        async def setup(self, c):
            pass

        async def teardown(self):
            pass

        async def invoke(self, ctx, **kw):
            captured["trace_id"] = ctx.trace_id
            return "ok"

    registry = PluginRegistry()
    registry.register(CapturingPlugin())

    result = await run_execute({"action": "cap", "action_input": {}, "trace_id": "trace-abc"}, registry, None, None)

    assert captured["trace_id"] == "trace-abc"
    assert result["last_tool_result"] == "ok"


@pytest.mark.asyncio
async def test_recall_falls_back_to_knowledge_and_writes_back():
    llm = MockLLMGateway([
        LLMResponse(content='[{"description": "x"}]', usage=Usage()),
        LLMResponse(content="退款政策：7天", usage=Usage()),
    ])
    long_term = FakeLongTermMemory()  # empty → recall insufficient
    knowledge = FakeKnowledge([KnowledgeEntry(id="k1", content="退款政策：7天", similarity=0.9)])
    deps = RuntimeDeps(
        llm=llm, retry=RetryPolicy(max_retries=0),
        long_term_memory=long_term, knowledge=knowledge, db=None,
    )

    result = await AgentRuntime().run(
        _def(), "退款政策？", RunContext(run_id="r1", tenant_id="t", user_id="u"), deps
    )

    assert result.status == "completed"
    assert "退款政策：7天" in long_term.added  # write-back into long-term memory
    plan_messages = llm.calls[0]["messages"]
    assert any("退款政策" in (m.get("content") or "") for m in plan_messages)
