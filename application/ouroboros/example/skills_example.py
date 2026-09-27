"""四形态 Skill：prompt / function / flow / agent，注册后交给 Agent 调用。

要点：
- Skill 是 kind="skill" 的插件，用 `SkillManager.build(record)` 从持久化 record 构建。
- flow/agent 需要宿主注入 `run_flow` / `run_subagent` 回调（经 RuntimeDeps 传入）。
- LLM 看到的函数名带 `skill_` 前缀，避免与 tool 撞名。
运行：``python example/skills_example.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.plugins.registry import PluginRegistry
from src.ports import InvokeContext
from src.skills.manager import SkillManager

from _shared import ScriptedLLM, finish, plan, tool_call


async def run_subagent(agent_ref: str, task: str, ctx) -> str:
    return f"[subagent:{agent_ref}] 完成：{task}"


async def run_flow(graph_spec: dict, ctx, kwargs: dict) -> str:
    return f"[flow:{graph_spec.get('name')}] 输入={kwargs.get('topic')}"


RECORDS = [
    {
        "name": "summarize",
        "type": "prompt",
        "description": "用三句话总结话题",
        "manifest": {
            "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        },
        "body": {"template": "请用三句话总结：{{topic}}"},
    },
    {
        "name": "make_brief",
        "type": "function",
        "description": "为某话题和受众生成任务简报",
        "manifest": {
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string"}, "audience": {"type": "string"}},
                "required": ["topic", "audience"],
            },
        },
        "body": {"source": "def run(**kw):\n    return f\"主题:{kw['topic']};受众:{kw['audience']}\""},
    },
    {
        "name": "quarterly",
        "type": "flow",
        "description": "跑一个预定义的季度复盘流程",
        "manifest": {
            "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        },
        "body": {"graph_spec": {"name": "quarterly-review"}},
    },
    {
        "name": "delegate",
        "type": "agent",
        "description": "把任务委派给专家子 Agent",
        "manifest": {
            "parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
        },
        "body": {"agent_ref": "research-specialist"},
    },
]


async def main() -> None:
    manager = SkillManager(run_subagent=run_subagent, run_flow=run_flow)
    registry = PluginRegistry()
    for record in RECORDS:
        registry.register(manager.build(record))

    # 1. 直接调用：不经过 Agent，逐个演示四种形态
    ctx = InvokeContext(run_id="skills-demo")
    print("== 直接调用四种 Skill ==")
    for name, args in [
        ("skill_summarize", {"topic": "季度复盘"}),
        ("skill_make_brief", {"topic": "季度复盘", "audience": "产品团队"}),
        ("skill_quarterly", {"topic": "季度复盘"}),
        ("skill_delegate", {"task": "分析用户反馈"}),
    ]:
        print(f"- {name}: {await registry.invoke(name, ctx, **args)}")

    # 2. 交给 Agent：LLM 选择 skill_make_brief
    llm = ScriptedLLM([
        plan("生成季度复盘任务简报"),
        tool_call("skill_make_brief", {"topic": "季度复盘", "audience": "产品团队"}),
        finish("简报已生成。"),
    ])
    definition = AgentDefinition(model="mock-model", system_prompt="你是项目助理", plugins=registry.all())
    deps = RuntimeDeps(llm=llm, subagent_runner=run_subagent, flow_runner=run_flow)
    result = await AgentRuntime().run(
        definition, "为产品团队生成季度复盘简报", RunContext(run_id="demo"), deps
    )
    print("\n== Agent 运行 ==")
    print("result:", result.result, "| steps:", [s.node for s in result.steps])


if __name__ == "__main__":
    asyncio.run(main())
