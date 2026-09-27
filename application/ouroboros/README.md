# Ouroboros

业务无关的 **Agent 框架层**。提供 Agent 运行循环（Plan → Decide → Execute → Observe）、统一插件协议、Skill/Tool 执行、记忆机制与能力端口（Ports）。

- **不依赖**业务层的 HTTP / 数据库 / 配置 / 多租户概念，可独立安装使用。
- 通过 `ports.py` 定义能力端口（`PermissionChecker` / `LongTermMemory` / `WorkingMemory` / `LLMGateway` / `Embedder` / `Plugin` 等），由宿主（业务层）实现并注入。

---

## 特性

| 能力 | 说明 |
|------|------|
| Agent 运行循环 | LangGraph 状态机：`Plan → Decide → Execute → Observe`，带迭代上限防死循环 |
| 统一插件协议 | `Plugin` / `PluginManifest`，Tool / Skill / Knowledge… 统一接入 |
| 工具执行 | 内置 `calculator`/`http`，支持 MCP 客户端、HTTP(OpenAPI) 适配 |
| 技能执行 | 四种形态：`prompt` / `function` / `flow` / `agent` |
| 记忆 | 短期 Working Brain（Redis）+ 会话固化 Consolidator + `LongTermMemory` 端口 |
| 授权 | 纯逻辑 `check_permission`（admin 绕过 / deny 优先 / 默认拒绝 / 高危审批） |
| 事件 | 运行时事件模型（非传输层） |

---

## 安装

```bash
pip install ouroboros        # 发布后

# monorepo 内以 path 依赖（开发态）
# 宿主工程的 pyproject.toml：
#   [tool.poetry.dependencies]
#   ouroboros = { path = "ouroboros", develop = true }
```

依赖：`python>=3.11`、`langgraph`、`litellm`、`pydantic`、`httpx`、`redis`。

---

## 目录结构

```
src/
├── ports.py          # 能力端口 + 权限/记忆数据类型（框架与宿主的契约）
├── state.py          # AgentState（循环内共享状态）
├── core/
│   ├── runtime.py     # AgentRuntime 门面（run/resume + 强类型）
│   ├── resilience.py  # RetryPolicy / CircuitBreaker
│   ├── checkpointer.py# InMemoryCheckpointer（默认实现）
│   └── nodes/         # plan / decide / execute / observe
├── plugins/          # Plugin 协议 + PluginRegistry + ref 解析
├── skills/           # prompt/function/flow/agent 四类 Skill
├── tools/            # builtin / MCP / HTTP(OpenAPI) 工具
├── memory/           # WorkingBrain + Consolidator + MemoryManager 门面
├── events/           # 运行时事件模型（run.started/step.completed/…）
└── llm/              # LLMGateway/Embedder 协议 + LiteLLM 实现
```

---

## 快速开始

```python
import asyncio

from src import AgentDefinition, AgentRuntime, RunContext, RuntimeDeps
from src.llm.litellm_gateway import LiteLLMGateway
from src.plugins.registry import PluginRegistry
from src.tools.registry import build_default_registry


async def main():
    # 1. 装配插件（内置 calculator / http）
    registry = PluginRegistry()
    for tool in build_default_registry().all():
        registry.register_tool(tool)

    # 2. 强类型门面：AgentDefinition（装配什么）+ RuntimeDeps（注入哪些端口）
    definition = AgentDefinition(model="deepseek-chat", system_prompt="你是助手", plugins=registry.all())
    deps = RuntimeDeps(llm=LiteLLMGateway(model="deepseek-chat", api_key="sk-..."))

    # 3. 运行 → RunResult（强类型，不再是裸 dict）
    result = await AgentRuntime().run(
        definition, "计算 3*8 再加 100", RunContext(run_id="demo", session_id="s1"), deps
    )
    print(result.status, result.result)      # completed, 3*8+100 = 124
    print(result.steps, result.token_usage)


asyncio.run(main())
```

`RuntimeDeps` 只要求 `llm`；其余端口（`permission_checker` / `long_term_memory` / `knowledge` / `event_sink` / `checkpointer` / `tracer` / `metrics` …）按需注入，全部契约集中在 `src.ports`。

---

## 核心概念

### AgentState（白板式共享状态）

四个节点不互相传参，而是读写同一份 `AgentState`（`TypedDict`）。节点返回一个 dict，LangGraph 自动 merge 回状态。

关键字段：`task` / `messages` / `plan` / `action` / `action_input` / `last_tool_result` / `iteration` / `max_iterations` / `status` / `result` / `memory_ctx` / `approvals` / `subagent_depth` / `token_usage`。

### 运行循环

```
plan ─► decide ─► execute ─► observe ─┐
                            ▲         │ (未完成)
                            └─ decide ◄┘
                                      │ (action=="__finish__" 或 iteration 触顶)
                                      ▼ END
```

| 节点 | 职责 |
|------|------|
| `plan` | 拆解任务为步骤清单（失败退化为单步） |
| `decide` | 带工具 schema 调 LLM，选择插件或收尾给答案 |
| `execute` | 权限校验后调用插件，归一化结果为字符串 |
| `observe` | 回填结果、`iteration+1`、触顶兜底 |

---

## 能力端口（Ports）

框架定义端口、宿主实现。全部在 `ports.py`。

### PermissionChecker

```python
from src.ports import PermissionChecker, PermissionContext, PermissionDecision, check_permission

class MyPermissionChecker(PermissionChecker):
    def check(self, ctx, action, resource_type, resource_id,
              resource_permission="read", requires_approval=False, approved=None):
        return check_permission(ctx, action, resource_type, resource_id,
                                resource_permission=resource_permission,
                                requires_approval=requires_approval, approved=approved)
```

`PermissionContext`：`permission_codes: set[str]`、`grant_keys: set[(resource_type, resource_id, effect)]`、`is_admin: bool`。

判定顺序：**admin 绕过 → 功能权限 `run:execute` → deny 优先 → read 默认放行 → grant 要求 → 高危审批**。

### LongTermMemory / WorkingMemory

```python
from src.ports import LongTermMemory, MemoryEntry

class InMemoryLongTerm(LongTermMemory):
    async def add(self, db, *, tenant_id, user_id, session_id, content,
                  importance=0.5, confidence=0.5) -> str: ...
    async def recall(self, db, tenant_id, user_id, query, top_k=5) -> list[MemoryEntry]: ...
```

> `db` 参数由宿主传入（如 `AsyncSession`），协议不约束其类型。框架自带的 Redis 实现见 `src.memory.working.WorkingBrain`。

### Embedder

```python
from src.llm.embedder import LiteLLMEmbedder, HashEmbedder

embedder = LiteLLMEmbedder("text-embedding-3-small", api_key="sk-...")  # 有 key
embedder = HashEmbedder(1536)                                          # 离线回退（确定性 hash）
```

---

## 开发自定义 Tool

```python
from src.tools.base import BaseTool, ToolResult

class WeatherTool(BaseTool):
    name = "weather"
    description = "查询城市天气"
    permission = "read"              # read | write | admin
    parameters = {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "城市名"}},
        "required": ["city"],
    }

    async def run(self, city: str) -> ToolResult:
        return ToolResult(success=True, output=f"{city}：晴 22℃")


registry.register_tool(WeatherTool())   # 内部用 ToolAsPlugin 适配成 Plugin
```

---

## 开发自定义 Skill

Skill 是 `kind="skill"` 的插件，四种形态，用 `PluginManifest` 声明能力：

```python
from src.plugins.base import PluginManifest
from src.plugins.registry import PluginRegistry
from src.skills.prompt_skill import PromptSkill
from src.skills.function_skill import FunctionSkill
from src.skills.agent_skill import AgentSkill
from src.skills.flow_skill import FlowSkill

registry = PluginRegistry()

registry.register(PromptSkill(           # prompt：模板渲染
    PluginManifest(name="refund_policy", kind="skill"),
    {"template": "退款政策：7 天无理由（上下文：{{memory_ctx}}）"},
))

registry.register(FunctionSkill(         # function：执行 Python（非沙箱，仅可信作者）
    PluginManifest(name="add", kind="skill"),
    {"source": "def run(**kw):\n    return str(int(kw['a']) + int(kw['b']))"},
))

registry.register(AgentSkill(            # agent：调子 Agent（注入 run_subagent 回调）
    PluginManifest(name="escalate", kind="skill"),
    {"agent_ref": "agent_escalation"},
    run_subagent=my_subagent_runner,
))

registry.register(FlowSkill(             # flow：多步流程（注入 run_flow 回调）
    PluginManifest(name="report", kind="skill"),
    {"graph_spec": {}},
    run_flow=my_flow_runner,
))
```

`PluginManifest` 字段：`name / version / kind / description / parameters(JSON Schema) / permission / requires_approval / dependencies / tags`。

---

## 插件引用与命名

```python
from src.plugins.manifest import parse_ref, format_ref

parse_ref("tool:calculator")        # PluginRef(kind="tool", name="calculator")
parse_ref("skill:refund@1.2.0")     # PluginRef(kind="skill", name="refund", version="1.2.0")
format_ref("skill", "refund", "1.2.0")  # "skill:refund@1.2.0"
```

**`function_name` 命名空间**：`tool` 用裸名（`calculator`），非 `tool` 种类加前缀（`skill_refund_policy`），避免 function-calling 撞名。LLM 返回的 `tool_call.name` 即 `function_name`，可被 `PluginRegistry.get()` 反查。

---

## 事件与流式

经 `RuntimeDeps.event_sink` 注入异步回调，每步产出一个 `RuntimeEvent`（`run.started` / `step.completed` / `run.completed` / …）：

```python
async def sink(event):
    print(event.event, event.data)   # 框架只出数据；SSE/WebSocket 序列化由宿主做

deps = RuntimeDeps(llm=llm, event_sink=sink)
```

事件类型：`run.started` / `step.completed` / `run.completed` / `run.failed` / `run.awaiting_human` / `run.approved` / `run.rejected`。框架只产出事件数据，传输由宿主负责。

---

## 记忆编排

```python
from src.memory.manager import MemoryManager
from src.memory.consolidator import Consolidator
from src.memory.working import WorkingBrain

manager = MemoryManager(
    working=WorkingBrain(redis_client),
    vector_store=my_long_term_memory,                          # 实现 LongTermMemory
    consolidator=Consolidator(my_long_term_memory, similarity_threshold=0.85),
)

await manager.write(session_id, {"role": "user", "content": "..."})    # 短期写入
history = await manager.get_history(session_id)                       # 短期读取
entries = await manager.recall(db, tenant_id, user_id, query, top_k=5) # 长期召回
await manager.consolidate(db, session_id, tenant_id, user_id)          # 短期→长期固化
```

---

## 完整示例

`example/` 目录下有每个模块的可运行示例（权限/HITL、事件流式、记忆、知识、可靠性、多厂商 fallback、评测等）。典型的高危审批 + 恢复流程：

```python
result = await runtime.run(definition, "删除账号 u42", context, deps)
# result.status == "awaiting_human", result.pending_approvals = [...]

resumed = await runtime.resume(definition, "run-1", ["delete_account"], deps)
# resumed.status == "completed"
```

详见 `example/permissions_hitl.py`。

---

## API 速查

| 符号 | 位置 | 签名 |
|------|------|------|
| `AgentRuntime` | `core.runtime` | `run(definition, task, context, deps) -> RunResult` / `resume(...)` |
| `RuntimeDeps` | `core.runtime` | `llm / permission_checker / long_term_memory / knowledge / event_sink / checkpointer / tracer / metrics / retry …` |
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

## 运行测试

```bash
cd ouroboros
poetry install
poetry run pytest            # 168 个单元测试，无外部依赖（Redis/LLM/DB 均用 fake）
```

---

## 日志

框架用标准库 `logging` 在 `ouroboros` 命名空间下输出日志（`src.core.runtime`、`src.core.nodes.execute` …），**从不自行配置 handler/level**——是否开启由宿主决定。

宿主开启：

```python
import logging
from src.log import configure_logging

configure_logging(level=logging.INFO)   # 或 logging.DEBUG 看更细
```

也可直接用宿主自己的 logging 配置（`ouroboros` 已挂 `NullHandler`，不会产生 "no handler" 噪音，且会传播到根 logger）。

级别约定：

| 级别 | 场景 |
|------|------|
| `DEBUG` | 每步节点/耗时、LLM 调用元数据、插件/工具注册 |
| `INFO` | run 开始/完成、待审批 |
| `WARNING` | 越权拒绝、未知插件、LLM 失败回退、迭代触顶、工具执行失败 |
| `ERROR`（含堆栈）| run 失败、插件抛出异常 |

> 不记录敏感数据：`api_key`、消息内容、工具入参均不落日志。

---

## 设计原则

1. **依赖倒置**：框架只依赖 `ports.py` 的协议与纯数据，不 import 宿主的存储/HTTP/配置。
2. **单一路径执行**：无论 Tool/Skill，`execute` 都走 `registry.get(action) → invoke`。
3. **声明与实现分离**：`manifest` 描述「是什么」，`body`/`run` 描述「怎么做」。
4. **容错收敛**：LLM 失败退化为单步计划、空输出即收尾、迭代上限兜底，保证不死循环。
5. **权限在执行前**：不信任 LLM 的选择，`execute` 前强制校验。
