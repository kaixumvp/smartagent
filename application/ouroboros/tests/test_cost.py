import pytest

from src.llm.base import LLMResponse, Usage
from src.llm.cost import (
    CachingGateway,
    TieredRouter,
    TokenBudget,
    message_length_classifier,
)


class Counting:
    def __init__(self):
        self.calls = 0

    async def chat(self, messages, model=None, tools=None):
        self.calls += 1
        return LLMResponse(content="x", usage=Usage(total_tokens=1))


@pytest.mark.asyncio
async def test_caching_gateway_reuses_identical_prompt():
    inner = Counting()
    cache = CachingGateway(inner)
    await cache.chat([{"role": "user", "content": "hi"}])
    await cache.chat([{"role": "user", "content": "hi"}])
    assert inner.calls == 1
    assert cache.hits == 1
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_tiered_router_chooses_model_by_complexity():
    inner = Counting()
    router = TieredRouter(inner, "cheap-model", "expensive-model", message_length_classifier(10))
    await router.chat([{"role": "user", "content": "hi"}])
    assert router.last_model == "cheap-model"
    await router.chat([{"role": "user", "content": "x" * 20}])
    assert router.last_model == "expensive-model"


def test_token_budget_consume_and_exhaust():
    b = TokenBudget(10)
    assert b.consume({"total_tokens": 6}) is True
    assert b.used == 6
    assert b.consume({"total_tokens": 4}) is True  # exactly at budget
    assert b.exhausted is True
    assert b.consume({"total_tokens": 1}) is False  # over budget


@pytest.mark.asyncio
async def test_runtime_aborts_on_token_budget():
    from conftest import MockLLMGateway, build_default_plugins
    from src import AgentDefinition, AgentRuntime, RunContext, RuntimeConfig, RuntimeDeps
    from src.core.resilience import RetryPolicy

    # plan alone consumes 15 tokens, exceeding the budget of 10
    llm = MockLLMGateway([
        LLMResponse(
            content='[{"description": "x"}]',
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        ),
    ])
    definition = AgentDefinition(
        model="m", system_prompt="s", plugins=build_default_plugins(),
        runtime=RuntimeConfig(max_total_tokens=10),
    )
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=0))

    result = await AgentRuntime().run(definition, "计算", RunContext(run_id="r1"), deps)

    assert result.status == "failed"
    assert "token budget exceeded" in (result.error or "")


@pytest.mark.asyncio
async def test_caching_gateway_evicts_oldest():
    inner = Counting()
    cache = CachingGateway(inner, max_size=2)
    for content in ["a", "b", "c"]:
        await cache.chat([{"role": "user", "content": content}])
    await cache.chat([{"role": "user", "content": "a"}])  # "a" was evicted → miss again

    assert inner.calls == 4
    assert cache.hits == 0
    assert cache.misses == 4
