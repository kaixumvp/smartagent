"""确定性重放（V1.1）：record 一次 run 的 LLM 响应，离线 replay 出相同结果。

要点：
- `RecordingGateway` 在跑 LLM 时把每次 `chat` 响应按序记录下来。
- `ReplayGateway` 按序回放记录，完全脱离真实 LLM，用于离线评测/回归。
- 同一 run 重放产出相同的 `RunResult`（status/result/steps 一致）。
运行：``python example/replay.py``
"""

import asyncio
import os
import tempfile

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.core.resilience import RetryPolicy
from src.llm.replay import ReplayGateway, RecordingGateway, dump_recording, load_recording
from src.plugins.registry import PluginRegistry
from src.tools.registry import build_default_registry

from _shared import ScriptedLLM, finish, plan, tool_call


def build_definition() -> AgentDefinition:
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)
    return AgentDefinition(model="mock-model", system_prompt="你是助手", plugins=registry.all())


async def main() -> None:
    definition = build_definition()
    rt = AgentRuntime()

    # 1. 用「真」LLM 跑一次，同时记录响应
    real_llm = ScriptedLLM([
        plan("计算 3*8+100"),
        tool_call("calculator", {"expression": "3*8+100"}),
        finish("3*8+100 = 124"),
    ])
    recorder = RecordingGateway(real_llm)
    first = await rt.run(definition, "计算 3*8+100", RunContext(run_id="r1"),
                         RuntimeDeps(llm=recorder, retry=RetryPolicy(max_retries=0)))

    # 2. 落盘再读回（可选，用于跨进程离线评测）
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "recording.json")
        dump_recording(recorder.recorded, path)
        loaded = load_recording(path)

    # 3. 离线重放：不再碰真实 LLM
    replay = ReplayGateway(loaded)
    second = await rt.run(definition, "计算 3*8+100", RunContext(run_id="r1"),
                          RuntimeDeps(llm=replay, retry=RetryPolicy(max_retries=0)))

    print("首次 status/result:", first.status, first.result)
    print("重放 status/result:", second.status, second.result)
    print("是否可复现:", first.status == second.status and first.result == second.result)


if __name__ == "__main__":
    asyncio.run(main())
