"""事件与流式：EventSink 端口产出 RuntimeEvent，宿主自行序列化（如 SSE）。

要点：
- 框架只产出 RuntimeEvent 数据对象（无传输）；SSE/WebSocket 序列化是宿主的事。
- 经 RuntimeDeps.event_sink 注入一个 async 回调，即可收到 run.started / step.completed / run.completed 等事件。
运行：``python example/events_streaming.py``
"""

import asyncio
import json

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.plugins.registry import PluginRegistry
from src.tools.registry import build_default_registry

from _shared import ScriptedLLM, finish, plan, tool_call


def to_sse(event) -> str:
    """宿主侧的 SSE 序列化示例（框架不内置）。"""
    return f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


async def main() -> None:
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)

    events = []

    async def sink(event) -> None:
        events.append(event)
        print(to_sse(event))

    llm = ScriptedLLM([
        plan("计算 3*8+100"),
        tool_call("calculator", {"expression": "3*8+100"}),
        finish("3*8+100 = 124"),
    ])
    definition = AgentDefinition(model="mock-model", system_prompt="你是助手", plugins=registry.all())
    deps = RuntimeDeps(llm=llm, event_sink=sink)

    result = await AgentRuntime().run(
        definition, "计算 3*8+100", RunContext(run_id="demo"), deps
    )

    print("\n收到的 RuntimeEvent 类型:", [e.event for e in events])
    print("最终状态:", result.status)


if __name__ == "__main__":
    asyncio.run(main())
