"""记忆：短期 Working + 长期 Vector + 固化/评分/遗忘，并让 Agent 召回。

要点：
- WorkingMemory（短期，会话内）→ Consolidator（固化：抽取 + reflect 评分 + 相似去重 + 遗忘阈值）→ LongTermMemory（长期）。
- MemoryManager 是门面；Agent 通过 RuntimeDeps.long_term_memory 在计划阶段召回记忆（memory_ctx）。
- 这里用内存版实现演示；生产换成 Redis / pgvector 即可（协议不变）。
运行：``python example/memory.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.memory.consolidator import Consolidator
from src.memory.manager import MemoryManager
from src.memory.reflect import Reflector
from src.ports import LongTermMemory, MemoryEntry, WorkingMemory

from _shared import ScriptedLLM, finish, plan, tool_call


class InMemoryWorking(WorkingMemory):
    """短期记忆的内存版（生产用 Redis 的 WorkingBrain 替换）。"""

    def __init__(self) -> None:
        self._hist: dict[str, list[dict]] = {}

    async def get_history(self, session_id: str) -> list[dict]:
        return list(self._hist.get(session_id, []))

    async def append(self, session_id: str, message: dict) -> None:
        self._hist.setdefault(session_id, []).append(message)


class InMemoryLongTerm(LongTermMemory):
    """长期记忆的内存版（生产用 pgvector 实现替换）。"""

    def __init__(self) -> None:
        self._items: list[MemoryEntry] = []
        self._seq = 0

    async def add(self, db, *, tenant_id, user_id, session_id, content, importance=0.5, confidence=0.5) -> str:
        self._seq += 1
        self._items.append(MemoryEntry(
            id=f"m{self._seq}", tenant_id=tenant_id, user_id=user_id, session_id=session_id,
            content=content, importance=importance, confidence=confidence,
        ))
        return f"m{self._seq}"

    async def recall(self, db, tenant_id, user_id, query, top_k=5) -> list[MemoryEntry]:
        # 简化：全量返回以演示注入；生产用 embedding 相似度检索
        return self._items[:top_k]


async def main() -> None:
    working = InMemoryWorking()
    long_term = InMemoryLongTerm()
    consolidator = Consolidator(long_term, importance_threshold=0.5, reflector=Reflector())
    manager = MemoryManager(working=working, vector_store=long_term, consolidator=consolidator)

    # 1. 短期写入
    await manager.write("s1", {"role": "user", "content": "我总喜欢深色主题"})
    await manager.write("s1", {"role": "assistant", "content": "好的，已记住"})
    print("短期历史:", await manager.get_history("s1"))

    # 2. 固化到长期：低价值的 "ok" 会被遗忘，偏好类会被保留
    await working.append("s1", {"role": "user", "content": "ok"})
    inserted = await manager.consolidate(None, "s1", "t1", "u1")
    print(f"固化 {inserted} 条（'ok' 因重要性 < 0.5 被遗忘）")

    # 3. Agent 配合运行：计划阶段召回长期记忆注入 memory_ctx
    llm = ScriptedLLM([
        plan("回答关于主题偏好的问题"),
        finish("用户偏好深色主题。"),
    ])
    definition = AgentDefinition(model="mock-model", system_prompt="你是助手", plugins=[])
    deps = RuntimeDeps(llm=llm, long_term_memory=long_term, db=None)
    await AgentRuntime().run(definition, "我喜欢什么主题？", RunContext(run_id="demo", tenant_id="t1", user_id="u1"), deps)

    # 观察 plan 节点收到的 messages：记忆内容被注入为 system 上下文
    plan_messages = llm.calls[0]["messages"]
    memory_ctx = [m for m in plan_messages if "深色主题" in (m.get("content") or "")]
    print("计划节点是否收到召回记忆:", "是" if memory_ctx else "否")


if __name__ == "__main__":
    asyncio.run(main())
