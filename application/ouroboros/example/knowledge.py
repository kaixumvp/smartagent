"""知识：Knowledge/Retriever 端口 + KnowledgePlugin，记忆不足时自动回退知识。

要点：
- `Knowledge`/`Retriever` 是端口：RAG 流水线（摄取/切块/embedding/rerank）由宿主实现。
- `KnowledgePlugin` 把检索包装成 kind="knowledge" 的插件，Agent 可以像调工具一样调它。
- Agent 计划阶段：长期记忆不足（sufficiency 判定失败）时，自动回退知识检索并回写记忆。
运行：``python example/knowledge.py``
"""

import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.knowledge import KnowledgePlugin
from src.ports import InvokeContext, KnowledgeEntry, LongTermMemory, MemoryEntry

from _shared import ScriptedLLM, finish, plan, tool_call


class InMemoryKnowledge:
    """知识端口的内存实现（生产替换成真实 RAG 流水线）。"""

    def __init__(self, docs: list[KnowledgeEntry]) -> None:
        self._docs = docs

    async def search(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        # 简化：全量返回以演示回退；生产用 RAG 检索（embedding + rerank）
        return self._docs[:top_k]

    async def retrieve(self, query: str, top_k: int = 5) -> list[KnowledgeEntry]:
        return await self.search(query, top_k)

    async def add(self, *, content: str, source: str | None = None, metadata: dict | None = None) -> str:
        return "k1"


class EmptyLongTerm(LongTermMemory):
    """长期记忆为空 → 触发知识回退。"""

    def __init__(self) -> None:
        self.added: list[str] = []

    async def add(self, db, *, tenant_id, user_id, session_id, content, importance=0.5, confidence=0.5) -> str:
        self.added.append(content)
        return str(len(self.added))

    async def recall(self, db, tenant_id, user_id, query, top_k=5) -> list[MemoryEntry]:
        return []


async def main() -> None:
    knowledge = InMemoryKnowledge([
        KnowledgeEntry(id="k1", content="公司退款政策：7 天无理由退货", source="policy.md", similarity=0.9),
    ])

    # 1. 知识作为插件：Agent 可显式调用（函数名带 knowledge_ 前缀）
    plugin = KnowledgePlugin("policy", "查询公司政策", knowledge)
    print("KnowledgePlugin 函数名:", plugin.manifest.function_name)
    print("直接检索:", await plugin.invoke(InvokeContext(run_id="demo"), query="退款政策"))

    # 2. 知识回退：长期记忆为空 → 计划阶段自动检索知识并回写
    long_term = EmptyLongTerm()
    llm = ScriptedLLM([
        plan("回答退款政策问题"),
        finish("7 天无理由退货。"),
    ])
    definition = AgentDefinition(model="mock-model", system_prompt="你是客服助手", plugins=[])
    deps = RuntimeDeps(llm=llm, long_term_memory=long_term, knowledge=knowledge, db=None)
    await AgentRuntime().run(definition, "退款政策是什么？", RunContext(run_id="demo"), deps)

    print("知识回写进长期记忆:", long_term.added)
    plan_messages = llm.calls[0]["messages"]
    has_knowledge = any("退款政策" in (m.get("content") or "") for m in plan_messages)
    print("计划节点是否注入知识上下文:", "是" if has_knowledge else "否")


if __name__ == "__main__":
    asyncio.run(main())
