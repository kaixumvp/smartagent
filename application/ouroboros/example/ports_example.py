"""能力端口（Ports）全景：实现并注入全部契约，跑一个完整 Agent。

框架只依赖 ports.py 的协议；宿主实现它们并通过 RuntimeDeps 注入。本例实现：
LLMGateway / PermissionChecker / LongTermMemory / Knowledge / EventSink / Checkpointer，
子 Agent 回调经 SkillManager 注入，然后一次性接线跑起来。
运行：``python example/ports_example.py``
"""

import asyncio

from ouroboros import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from ouroboros.core.checkpointer import InMemoryCheckpointer
from ouroboros.plugins.registry import PluginRegistry
from ouroboros.ports import (
    InvokeContext,
    KnowledgeEntry,
    LongTermMemory,
    MemoryEntry,
    PermissionContext,
    PermissionDecision,
    check_permission,
)
from ouroboros.skills.manager import SkillManager
from ouroboros.tools.registry import build_default_registry

from _shared import ScriptedLLM, finish, plan, tool_call


# ---- 各端口实现（宿主职责）----
class PermissionManager:
    def check(self, ctx, action, resource_type, resource_id,
              resource_permission="read", requires_approval=False, approved=None) -> PermissionDecision:
        return check_permission(ctx, action, resource_type, resource_id,
                                resource_permission, requires_approval, approved)


class InMemoryLongTerm(LongTermMemory):
    def __init__(self) -> None:
        self._items: list[MemoryEntry] = []
        self._seq = 0

    async def add(self, db, *, tenant_id, user_id, session_id, content, importance=0.5, confidence=0.5) -> str:
        self._seq += 1
        self._items.append(MemoryEntry(id=f"m{self._seq}", tenant_id=tenant_id, user_id=user_id,
                                       session_id=session_id, content=content, importance=importance))
        return f"m{self._seq}"

    async def recall(self, db, tenant_id, user_id, query, top_k=5) -> list[MemoryEntry]:
        return self._items[:top_k]


class InMemoryKnowledge:
    def __init__(self, docs: list[KnowledgeEntry]) -> None:
        self._docs = docs

    async def search(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        return self._docs[:top_k]

    async def retrieve(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        return await self.search(query, top_k)

    async def add(self, *, content: str, source: str | None = None, metadata: dict | None = None) -> str:
        return "k1"


async def main() -> None:
    # 子 Agent / 流程回调
    async def run_subagent(agent_ref: str, task: str, ctx) -> str:
        return f"[subagent:{agent_ref}] 完成：{task}"

    # 事件 sink
    events = []

    async def sink(event) -> None:
        events.append(event.event)

    # 装配插件：内置工具 + 一个 agent-skill
    manager = SkillManager(run_subagent=run_subagent)
    skill = manager.build({
        "name": "delegate", "type": "agent", "description": "委派给专家子 Agent",
        "manifest": {"parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}},
        "body": {"agent_ref": "research-specialist"},
    })
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)
    registry.register(skill)

    # 一次性注入全部端口
    llm = ScriptedLLM([
        plan("委派研究 Agent 分析反馈"),
        tool_call("skill_delegate", {"task": "分析用户反馈"}),
        finish("研究 Agent 已完成分析。"),
    ])
    deps = RuntimeDeps(
        llm=llm,
        permission_checker=PermissionManager(),
        permission_context=PermissionContext(permission_codes={"run:execute"}),
        long_term_memory=InMemoryLongTerm(),
        knowledge=InMemoryKnowledge([KnowledgeEntry(id="k1", content="公司退款政策")]),
        event_sink=sink,
        checkpointer=InMemoryCheckpointer(),
        db=None,
    )
    definition = AgentDefinition(model="mock-model", system_prompt="你是项目助理", plugins=registry.all())

    result = await AgentRuntime().run(
        definition, "分析用户反馈", RunContext(run_id="ports-demo", tenant_id="t1", user_id="u1"), deps
    )

    print("result:", result.result)
    print("steps :", [s.node for s in result.steps])
    print("事件流 :", events)


if __name__ == "__main__":
    asyncio.run(main())
