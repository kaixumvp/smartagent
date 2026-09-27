"""可靠性：Retry（指数退避）+ 熔断 + 超时 + 子 Agent 深度。

要点：
- `run_with_retry` / `CircuitBreaker` 是独立原语，也可经 RuntimeDeps.retry / circuit_breaker 注入 Agent。
- 运行时对每个节点应用 retry；工具瞬时失败会自动重试，持久失败则 run 置 failed。
- `RuntimeConfig.timeout_seconds` 到点中止 run；`max_subagent_depth` 在 execute 前拒绝过深的子 Agent。
运行：``python example/reliability.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeConfig, RuntimeDeps
from src.core.nodes.execute import run_execute
from src.core.resilience import CircuitBreaker, RetryPolicy, run_with_retry
from src.plugins.registry import PluginRegistry
from src.ports import PluginManifest
from src.skills.agent_skill import AgentSkill
from src.tools.base import BaseTool, ToolResult

from _shared import ScriptedLLM, finish, plan, tool_call


class FlakyTool(BaseTool):
    """前两次失败、第三次成功的工具，演示 retry。"""

    name = "flaky"
    description = "偶尔失败的工具"
    permission = "read"
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, **kwargs) -> ToolResult:
        self.calls += 1
        if self.calls < 3:
            raise RuntimeError("瞬时故障")
        return ToolResult(success=True, output="recovered")


async def retry_primitives() -> None:
    print("== 原语：retry ==")
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    print("结果:", await run_with_retry(flaky, policy=RetryPolicy(max_retries=3, base_delay=0)), "尝试次数:", calls["n"])

    print("== 原语：熔断 ==")
    breaker = CircuitBreaker(failure_threshold=2)

    async def fail():
        raise RuntimeError("x")

    for i in range(3):
        try:
            await run_with_retry(fail, policy=RetryPolicy(max_retries=0, base_delay=0), breaker=breaker)
        except Exception as exc:  # noqa: BLE001
            print(f"  第 {i+1} 次: {type(exc).__name__}")


async def retry_in_agent() -> None:
    print("\n== Agent 内重试 ==")
    flaky = FlakyTool()
    registry = PluginRegistry()
    registry.register_tool(flaky)

    llm = ScriptedLLM([
        plan("调用 flaky 工具"),
        tool_call("flaky", {}),
        finish("recovered"),
    ])
    definition = AgentDefinition(model="mock-model", system_prompt="你是助手", plugins=registry.all())
    deps = RuntimeDeps(llm=llm, retry=RetryPolicy(max_retries=3, base_delay=0))
    result = await AgentRuntime().run(definition, "跑 flaky", RunContext(run_id="demo"), deps)
    print("result:", result.result, "| flaky 实际调用次数:", flaky.calls)


async def timeout_in_agent() -> None:
    print("\n== Agent 超时 ==")

    class SlowLLM:
        async def chat(self, messages, model=None, tools=None):
            await asyncio.sleep(0.2)
            from src.llm.base import LLMResponse, Usage
            return LLMResponse(content="", usage=Usage())

    definition = AgentDefinition(
        model="mock-model", system_prompt="你是助手", plugins=[],
        runtime=RuntimeConfig(timeout_seconds=0.05),
    )
    result = await AgentRuntime().run(
        definition, "慢任务", RunContext(run_id="demo"), RuntimeDeps(llm=SlowLLM(), retry=RetryPolicy(max_retries=0))
    )
    print("status:", result.status, "| error:", result.error)


async def depth_guard() -> None:
    print("\n== 子 Agent 深度保护 ==")
    registry = PluginRegistry()
    registry.register(AgentSkill(PluginManifest(name="escalate", kind="skill"), {"agent_ref": "a"}))
    result = await run_execute(
        {"action": "escalate", "action_input": {}, "subagent_depth": 3, "max_subagent_depth": 3},
        registry, None, None,
    )
    print("execute 返回:", result["last_tool_result"])


async def main() -> None:
    await retry_primitives()
    await retry_in_agent()
    await timeout_in_agent()
    await depth_guard()


if __name__ == "__main__":
    asyncio.run(main())
