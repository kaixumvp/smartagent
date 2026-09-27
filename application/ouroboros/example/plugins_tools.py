"""自定义 Tool / Plugin：定义、注册，并让 Agent 调用。

要点：
- Tool（旧协议 `run()`）经 `ToolAsPlugin` 适配成 Plugin，与 Skill 统一执行。
- Plugin 协议更完整（setup/invoke/teardown 生命周期），可直接 register。
- 无论 Tool 还是 Plugin，最终都由 Agent 的 decide 节点从 OpenAI schema 里选择。
运行：``python example/plugins_tools.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.plugins.registry import PluginRegistry
from src.ports import InvokeContext, PluginManifest
from src.tools.base import BaseTool, ToolResult

from _shared import ScriptedLLM, finish, plan, tool_call


class WeatherTool(BaseTool):
    """旧协议 Tool：只实现 `run()`，权限/参数用类属性声明。"""

    name = "weather"
    description = "查询城市天气"
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名"}},
        "required": ["city"],
    }

    async def run(self, city: str) -> ToolResult:
        return ToolResult(success=True, output=f"{city}：晴 22℃")


class ClockPlugin:
    """完整 Plugin：带生命周期。可做 tool 之外任何 kind（skill/knowledge/...）。"""

    kind = "tool"

    def __init__(self) -> None:
        self._manifest = PluginManifest(
            name="now",
            kind="tool",
            description="返回当前时间（演示用占位）",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    async def setup(self, config: dict) -> None:
        print("  [ClockPlugin.setup]")

    async def teardown(self) -> None:
        print("  [ClockPlugin.teardown]")

    async def invoke(self, ctx: InvokeContext, **kw) -> str:
        return "12:00 (mock)"


async def main() -> None:
    # 1. 直接调用：不经过 Agent 也能跑 Tool / Plugin
    weather = WeatherTool()
    print("直接调用 WeatherTool:", (await weather.run(city="北京")).output)

    # 2. 注册：Tool 用 register_tool 适配；Plugin 直接 register
    registry = PluginRegistry()
    registry.register_tool(WeatherTool())
    registry.register(ClockPlugin())
    print("OpenAI schema 暴露的函数:",
          [s["function"]["name"] for s in registry.to_openai_schema()])

    # 3. 交给 Agent：LLM 根据 schema 选择调用
    llm = ScriptedLLM([
        plan("查询北京天气"),
        tool_call("weather", {"city": "北京"}),
        finish("北京今天晴，22℃"),
    ])
    definition = AgentDefinition(model="mock-model", system_prompt="你是助手", plugins=registry.all())
    result = await AgentRuntime().run(
        definition, "北京天气如何", RunContext(run_id="demo"), RuntimeDeps(llm=llm)
    )
    print("Agent result:", result.result, "| steps:", [s.node for s in result.steps])


if __name__ == "__main__":
    asyncio.run(main())
