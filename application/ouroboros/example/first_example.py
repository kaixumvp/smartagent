"""最小闭环：用 AgentRuntime 跑一个带工具调用的 Agent（离线，无需 key）。

这是最简入口——只注入一个 LLM 端口，其余全部走默认（无鉴权、无记忆、无 checkpointer）。
运行：``python example/first_example.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.plugins.registry import PluginRegistry
from src.tools.registry import build_default_registry

from _shared import ScriptedLLM, finish, plan, tool_call


async def main() -> None:
    # 1. 装配插件（内置 calculator / http）
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)

    # 2. LLM 端口：离线用脚本化 Mock；接真实模型见 _shared.real_llm()
    llm = ScriptedLLM([
        plan("计算 3*8 再加 100"),
        tool_call("calculator", {"expression": "3*8+100"}),
        finish("3*8+100 = 124"),
    ])

    # 3. 强类型门面：AgentDefinition（装配什么）+ RuntimeDeps（注入哪些端口）
    definition = AgentDefinition(model="mock-model", system_prompt="你是助手", plugins=registry.all())
    deps = RuntimeDeps(llm=llm)

    # 4. 运行 → RunResult（强类型，不再是裸 dict）
    result = await AgentRuntime().run(
        definition, "计算 3*8 再加 100", RunContext(run_id="demo"), deps
    )

    print("status:", result.status)          # completed
    print("result:", result.result)          # 3*8+100 = 124
    print("steps :", [s.node for s in result.steps])   # plan → decide → execute → observe → decide
    print("usage :", result.token_usage)


if __name__ == "__main__":
    asyncio.run(main())
