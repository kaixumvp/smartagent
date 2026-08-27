# Agent 框架使用文档（smartagent-core）

> 面向**框架使用者**（业务方 / 插件开发者）的操作指南。说明如何安装 `smartagent-core`、跑一个 Agent、实现能力端口、开发自定义 Tool/Skill。
> 设计层面的原理见 **《Agent框架层详细设计.md》** 与 **《技术方案设计.md》§3.1**。

---

## 1. 这是什么

`smartagent-core` 是业务无关的 Agent 框架，提供：

- **Agent 运行循环**：`Plan → Decide → Execute → Observe`（LangGraph 状态机）
- **统一插件协议**：`Plugin` / `PluginManifest`（Tool/Skill/Knowledge/… 均按此接入）
- **能力端口**：`LLMGateway` / `Embedder` / `PermissionChecker` / `WorkingMemory` / `LongTermMemory` 等，由宿主实现
- **技能/工具执行**：四种 Skill 形态 + Builtin/MCP/HTTP 工具
- **记忆机制**：短期 Working Brain + 长期记忆固化

框架**不依赖**业务层的 HTTP、数据库、配置、多租户概念，可独立安装使用。

---

## 2. 安装

```toml
# 业务工程的 pyproject.toml（monorepo 内以 path 依赖）
[tool.poetry.dependencies]
smartagent-core = { path = "agent-core", develop = true }
```

独立发布后，改用内部源安装：

```bash
poetry add smartagent-core
```

框架自身依赖：`langgraph`、`litellm`、`pydantic`、`httpx`、`redis`。

---

## 3. 核心概念速览

| 概念 | 类型 | 说明 |
|------|------|------|
| `AgentState` | `TypedDict` | 循环内共享状态（task/plan/messages/action/iteration/…） |
| `LLMGateway` | 端口 | 统一 LLM 调用抽象，返回 `LLMResponse` |
| `Embedder` | 端口 | 文本向量化抽象 |
| `Plugin` | 协议 | 能力单元（Tool/Skill 统一），`manifest` + `invoke` |
| `PluginRegistry` | 类 | 插件注册表，按名称/ref/函数名索引，转 OpenAI function schema |
| `PermissionChecker` | 端口 | 运行时授权判定（纯逻辑，数据由宿主预加载） |
| `WorkingMemory` / `LongTermMemory` | 端口 | 短期/长期记忆抽象 |
| `build_graph` / `run_agent` | 函数 | 组装并驱动运行循环 |

---

## 4. 快速开始：跑一个带工具调用的 Agent

```python
import asyncio

from smartagent_core.core.graph import build_graph, run_agent
from smartagent_core.llm.litellm_gateway import LiteLLMGateway
from smartagent_core.plugins.registry import PluginRegistry
from smartagent_core.tools.registry import build_default_registry


async def main():
    # 1. LLM 网关（显式传模型/密钥）
    llm = LiteLLMGateway(model="deepseek-chat", api_key="sk-...")

    # 2. 装配插件（内置 calculator/http 工具）
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)

    # 3. 编译运行图（default_model 用于 config 未指定 model 时）
    graph = build_graph(llm, registry, "deepseek-chat", {"system_prompt": "你是助手"})

    # 4. 构造初始状态
    state = {
        "agent_id": "agent_demo",
        "run_id": "run_demo",
        "session_id": "session_demo",
        "tenant_id": "default",
        "user_id": None,
        "task": "计算 3*8 再加 100",
        "messages": [{"role": "user", "content": "计算 3*8 再加 100"}],
        "iteration": 0,
        "max_iterations": 20,
        "status": "running",
        "subagent_depth": 0,
    }

    # 5. 运行，返回 (最终状态, 步骤列表)
    final, steps = await run_agent(graph, state)
    print(final["status"])        # completed | failed
    print(final["result"])        # 最终答案
    print(final["token_usage"])   # {"prompt_tokens":..,"completion_tokens":..,"total_tokens":..}
    for s in steps:
        print(s["seq"], s["node"], s.get("action"))


asyncio.run(main())
```

**说明**：
- `build_graph(llm, registry, default_model, agent_config=None, *, permission_manager=None, permission_context=None)`
  - `agent_config` 可含 `model` / `system_prompt`（`model` 优先级高于 `default_model`）。
  - `permission_manager` + `permission_context` 缺省时不鉴权（单测 / 无 IAM 场景）。
- `run_agent(graph, initial_state, on_step=None)` 返回 `(final_state, steps)`；`on_step` 是可选异步回调，用于流式/落库。

---

## 5. 实现能力端口

框架定义端口、宿主（业务层）提供实现。

### 5.1 PermissionChecker（授权）

```python
from smartagent_core.ports import (
    PermissionChecker, PermissionContext, PermissionDecision, check_permission,
)


class MyPermissionChecker(PermissionChecker):
    def check(self, ctx, action, resource_type, resource_id,
              resource_permission="read", requires_approval=False, approved=None):
        # 直接复用框架的纯逻辑；ctx 由业务预加载（RBAC+Grant 展开）
        return check_permission(
            ctx, action, resource_type, resource_id,
            resource_permission=resource_permission,
            requires_approval=requires_approval,
            approved=approved,
        )
```

`PermissionContext` 结构：`permission_codes: set[str]`、`grant_keys: set[(resource_type, resource_id, effect)]`、`is_admin: bool`。

> 判定顺序（`check_permission`）：admin 绕过 → 功能权限 `run:execute` → deny 优先 → read 默认放行 → grant 要求 → 高危审批。

### 5.2 LongTermMemory（长期记忆）

```python
from smartagent_core.ports import LongTermMemory, MemoryEntry


class InMemoryLongTerm(LongTermMemory):
    def __init__(self):
        self._items: list[MemoryEntry] = []

    async def add(self, db, *, tenant_id, user_id, session_id, content,
                  importance=0.5, confidence=0.5) -> str:
        eid = f"mem_{len(self._items)}"
        self._items.append(MemoryEntry(
            id=eid, tenant_id=tenant_id, user_id=user_id, session_id=session_id,
            content=content, importance=importance, confidence=confidence,
        ))
        return eid

    async def recall(self, db, tenant_id, user_id, query, top_k=5) -> list[MemoryEntry]:
        return [m for m in self._items if m.tenant_id == tenant_id][:top_k]
```

> `db` 参数由宿主传入（业务侧是 `AsyncSession`），框架协议不约束其类型。

### 5.3 WorkingMemory（短期记忆）

```python
from smartagent_core.ports import WorkingMemory

# 或直接使用框架自带的 Redis 实现
from smartagent_core.memory.working import WorkingBrain

brain = WorkingBrain(redis_client, window_size=20, ttl_seconds=86400)
```

### 5.4 Embedder（向量化）

```python
from smartagent_core.llm.embedder import LiteLLMEmbedder, HashEmbedder

# 有 embedding key 时
embedder = LiteLLMEmbedder("text-embedding-3-small", api_key="sk-...")
# 离线回退（确定性 hash，维度 1536）
embedder = HashEmbedder(1536)
```

---

## 6. 开发自定义 Tool

```python
from smartagent_core.tools.base import BaseTool, ToolResult


class WeatherTool(BaseTool):
    name = "weather"
    description = "查询城市天气"
    permission = "read"  # read | write | admin
    parameters = {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名"}},
        "required": ["city"],
    }

    async def run(self, city: str) -> ToolResult:
        return ToolResult(success=True, output=f"{city}：晴 22℃")


registry.register_tool(WeatherTool())
```

- `Tool` 协议（`smartagent_core.tools.base`）：`name / description / parameters(JSON Schema) / permission` + `async run(**kw) -> ToolResult`。
- 工具会被 `ToolAsPlugin` 适配成 `Plugin`，与 Skill 统一对待。
- 内置工具：`calculator`（AST 白名单求值）、`http`（GET/POST）。

---

## 7. 开发自定义 Skill

Skill 是 `kind="skill"` 的插件，四种形态，用 `PluginManifest` 声明能力：

```python
from smartagent_core.plugins.base import PluginManifest
from smartagent_core.plugins.registry import PluginRegistry
from smartagent_core.skills.prompt_skill import PromptSkill
from smartagent_core.skills.function_skill import FunctionSkill
from smartagent_core.skills.agent_skill import AgentSkill
from smartagent_core.skills.flow_skill import FlowSkill

registry = PluginRegistry()

# prompt：模板渲染
registry.register(PromptSkill(
    PluginManifest(name="refund_policy", kind="skill"),
    {"template": "退款政策：7 天无理由（上下文：{{memory_ctx}}）"},
))

# function：执行 Python 函数（非沙箱，仅可信作者使用）
registry.register(FunctionSkill(
    PluginManifest(name="add", kind="skill"),
    {"source": "def run(**kw):\n    return str(int(kw['a']) + int(kw['b']))"},
))

# agent：调子 Agent（需注入 run_subagent 回调）
registry.register(AgentSkill(
    PluginManifest(name="escalate", kind="skill"),
    {"agent_ref": "agent_escalation"},
    run_subagent=my_subagent_runner,
))

# flow：多步流程（需注入 run_flow 回调，V0.2 未接线）
registry.register(FlowSkill(
    PluginManifest(name="report", kind="skill"),
    {"graph_spec": {}},
    run_flow=my_flow_runner,
))
```

**`PluginManifest` 字段**：`name / version / kind / description / parameters(JSON Schema) / permission(read|write|admin) / requires_approval / dependencies / tags`。

**`function_name`**：工具用裸名（`calculator`），非 tool 种类加前缀防冲突（`skill_refund_policy`）。

---

## 8. 插件引用与注册

```python
from smartagent_core.plugins.manifest import parse_ref, format_ref

parse_ref("tool:calculator")       # PluginRef(kind="tool", name="calculator", version=None)
parse_ref("skill:refund@1.2.0")    # PluginRef(kind="skill", name="refund", version="1.2.0")
format_ref("skill", "refund", "1.2.0")  # "skill:refund@1.2.0"
```

`PluginRegistry` 按三种键索引插件：裸名、完整 ref、OpenAI function name。`to_openai_schema()` 产出给 LLM 的 function-calling 描述。

---

## 9. 事件与流式

运行循环每一步产出 `Step`（`seq/node/action/output/status/latency_ms`），通过 `on_step` 回调或 `events` 模块：

```python
from smartagent_core.events.sse import run_started, step_completed, run_completed

async def on_step(step):
    print(step_completed(step).serialize())  # "event: step.completed\ndata: {...}\n\n"
```

事件类型：`run.started` / `step.completed` / `run.completed` / `run.failed` / `run.awaiting_human` / `run.approved` / `run.rejected`。

> 框架只产出事件数据；SSE/HTTP 传输由宿主负责。

---

## 10. 记忆编排（MemoryManager 门面）

```python
from smartagent_core.memory.manager import MemoryManager
from smartagent_core.memory.consolidator import Consolidator
from smartagent_core.memory.working import WorkingBrain

manager = MemoryManager(
    working=WorkingBrain(redis_client),
    vector_store=my_long_term_memory,              # 实现 LongTermMemory 端口
    consolidator=Consolidator(my_long_term_memory, similarity_threshold=0.85),
)

await manager.write(session_id, {"role": "user", "content": "..."})   # 短期
entries = await manager.recall(db, tenant_id, user_id, query, top_k=5)  # 长期召回
await manager.consolidate(db, session_id, tenant_id, user_id)          # 会话固化
```

---

## 11. API 速查

| 符号 | 位置 | 签名 |
|------|------|------|
| `build_graph` | `core.graph` | `(llm, registry, default_model, agent_config=None, *, permission_manager=None, permission_context=None)` |
| `run_agent` | `core.graph` | `(graph, initial_state, on_step=None) -> (final_state, steps)` |
| `PluginRegistry` | `plugins.registry` | `register / register_tool / get / to_openai_schema / invoke` |
| `PluginManifest` | `plugins.base` | Pydantic 模型 + `function_name` |
| `InvokeContext` | `plugins.base` | `tenant_id/user_id/run_id/trace_id/session_id/subagent_depth` |
| `check_permission` | `ports` | `(ctx, action, resource_type, resource_id, *, resource_permission, requires_approval, approved)` |
| `Tool` / `BaseTool` / `ToolResult` | `tools.base` | 工具抽象 |
| `Skill` / `build_skill` | `skills.base` | 四形态技能 |
| `LiteLLMGateway` | `llm.litellm_gateway` | `(model, api_key, api_base)` |
| `LiteLLMEmbedder` / `HashEmbedder` | `llm.embedder` | 向量化 |
| `MemoryManager` / `WorkingBrain` / `Consolidator` | `memory.*` | 记忆编排 |

---

## 12. 完整示例（含权限 + 记忆 + 流式回调）

```python
import asyncio

from smartagent_core.core.graph import build_graph, run_agent
from smartagent_core.llm.litellm_gateway import LiteLLMGateway
from smartagent_core.plugins.registry import PluginRegistry
from smartagent_core.tools.registry import build_default_registry
from smartagent_core.ports import PermissionContext


async def main():
    llm = LiteLLMGateway(model="deepseek-chat", api_key="sk-...")
    registry = PluginRegistry()
    for t in build_default_registry().all():
        registry.register_tool(t)

    # 预加载授权上下文（业务层负责从 RBAC/Grant 展开）
    perm_ctx = PermissionContext(
        permission_codes={"run:execute"},
        grant_keys=set(),
        is_admin=False,
    )
    checker = MyPermissionChecker()  # 见 §5.1

    graph = build_graph(llm, registry, "deepseek-chat", {},
                        permission_manager=checker, permission_context=perm_ctx)

    steps_seen = []

    async def on_step(step):
        steps_seen.append(step)

    state = {
        "agent_id": "a1", "run_id": "r1", "session_id": "s1",
        "tenant_id": "default", "user_id": None,
        "task": "计算 3*8 再加 100",
        "messages": [{"role": "user", "content": "计算 3*8 再加 100"}],
        "iteration": 0, "max_iterations": 20,
        "status": "running", "subagent_depth": 0,
        "approvals": [],
    }

    final, _ = await run_agent(graph, state, on_step=on_step)
    print(final["status"], final["result"], len(steps_seen))


asyncio.run(main())
```
