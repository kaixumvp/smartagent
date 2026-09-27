"""成本感知（V1.1）：prompt 缓存复用 + 模型分级路由 + token 预算。

要点：
- `CachingGateway`：相同 prompt 命中缓存，不再调底层 LLM。
- `TieredRouter` + `message_length_classifier`：简单任务走小模型，复杂走大模型。
- `RuntimeConfig.max_total_tokens`：运行期 token 预算，超限自动中止 run。
运行：``python example/cost.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeConfig, RuntimeDeps
from src.core.resilience import RetryPolicy
from src.llm.base import LLMResponse, Usage
from src.llm.cost import CachingGateway, TieredRouter, TokenBudget, message_length_classifier
from src.plugins.registry import PluginRegistry
from src.tools.registry import build_default_registry

from _shared import ScriptedLLM


class Counting:
    """记录调用次数的简单 LLM。"""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, model=None, tools=None):
        self.calls += 1
        return LLMResponse(content="ok", usage=Usage(total_tokens=1))


async def cache_demo() -> None:
    inner = Counting()
    cache = CachingGateway(inner)
    await cache.chat([{"role": "user", "content": "hi"}])
    await cache.chat([{"role": "user", "content": "hi"}])
    print(f"[缓存] 底层 LLM 调用 {inner.calls} 次，命中 {cache.hits} 次")


async def router_demo() -> None:
    inner = Counting()
    router = TieredRouter(inner, "cheap-model", "expensive-model", message_length_classifier(10))
    await router.chat([{"role": "user", "content": "hi"}])
    print(f"[分级路由] 短任务 → {router.last_model}")
    await router.chat([{"role": "user", "content": "x" * 50}])
    print(f"[分级路由] 长任务 → {router.last_model}")


async def budget_demo() -> None:
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)

    # plan 单次消耗 15 token，超过预算 10 → run 中止
    llm = ScriptedLLM([
        LLMResponse(content='[{"description": "x"}]',
                    usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
    ])
    definition = AgentDefinition(
        model="m", system_prompt="s", plugins=registry.all(),
        runtime=RuntimeConfig(max_total_tokens=10),
    )
    result = await AgentRuntime().run(
        definition, "计算", RunContext(run_id="r1"), RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=0))
    )
    print(f"[预算] status={result.status}, error={result.error}")

    b = TokenBudget(100)
    b.consume({"total_tokens": 40})
    print(f"[预算] 消耗 40 → 剩余 {b.remaining}")


async def main() -> None:
    await cache_demo()
    await router_demo()
    await budget_demo()


if __name__ == "__main__":
    asyncio.run(main())
