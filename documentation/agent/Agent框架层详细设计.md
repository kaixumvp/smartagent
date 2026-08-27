# Agent 框架层详细设计（smartagent-core）

> 对应《技术方案设计.md》§3.1 的下半层。本文档定义**业务无关的 Agent 框架层**的职责、目录、核心抽象、能力端口（Ports）与内部机制。
> 框架层回答一个问题：**「给定一个 Agent 定义 + 任务 + 一组能力，如何跑出结果」**。它不关心租户、数据库、HTTP、鉴权。

---

## 1. 定位与职责边界

### 1.1 职责（做）

| 职责 | 说明 |
|------|------|
| Agent 编排 | LangGraph 主循环 `Plan → Decide → Execute → Observe` 的装配与驱动 |
| 能力协议 | 定义 `Plugin` / `PluginManifest` 统一协议，Tool/Skill/Knowledge/Model/Memory 均可接入 |
| 端口抽象 | 定义 `LLMGateway`/`Embedder`/`PermissionChecker`/`Memory`/`EventSink` 等能力端口 |
| 技能/工具执行 | 四种 Skill 形态、Builtin/MCP/HTTP 工具的**执行**逻辑 |
| 记忆机制 | Working Brain 短期记忆、Consolidator 会话固化、LongTermMemory 协议 |
| 事件模型 | 运行时事件的数据结构（不含 HTTP/SSE 传输） |
| 默认实现 | LiteLLM 网关、Hash/LiteLLM 嵌入器、Redis 工作记忆等开箱即用实现 |

### 1.2 不职责（不做 / 由业务层负责）

- 不做 HTTP 路由、认证、租户隔离、限流（业务层 `api/`）
- 不做 Agent/Tool/Skill/Run 的持久化与 CRUD（业务层 `persistence/`）
- 不做「从 DB 装配插件」（业务层 `adapters/db_plugin_loader.py`）
- 不做 RBAC/Grant 的**数据加载**（业务层 `adapters/db_permission.py`；框架只做 `check()` 纯逻辑）
- 不 import `fastapi`、`sqlalchemy` 模型、业务 `config`、租户概念

### 1.3 设计原则

1. **依赖倒置**：框架只依赖 `ports.py` 的 Protocol 与纯数据（pydantic/dataclass），不依赖任何具体存储/传输。
2. **单向依赖**：框架内部 `runtime → core → plugins/skills/tools/memory`，禁止反向 import；框架禁止 import 业务层。
3. **默认可跑**：`default/` 提供最小可用实现，业务层可选覆盖。
4. **配置外置**：运行时参数经 `RuntimeConfig` 传入，框架不读 `.env`。

---

## 2. 目录结构（文件级）

```
agent-core/
├── pyproject.toml               # name = "smartagent-core"
├── README.md
└── src/smartagent_core/
    ├── runtime.py               # AgentRuntime：编排入口（§5）
    ├── ports.py                 # 全部能力端口 + 核心数据类型（§3/§4）
    ├── state.py                 # AgentState（循环内共享状态）
    ├── core/
    │   ├── graph.py             # LangGraph 图装配 + run_agent 流式驱动
    │   └── nodes/
    │       ├── plan.py          # 任务拆解
    │       ├── decide.py        # 选择插件 / 结束
    │       ├── execute.py       # 授权后调用插件
    │       └── observe.py       # 结果回填 + 迭代控制
    ├── plugins/
    │   ├── base.py              # Plugin 协议 + PluginManifest + InvokeContext + ToolAsPlugin
    │   ├── manifest.py          # ref 解析（kind:name@version）
    │   └── registry.py          # PluginRegistry（多键索引 + OpenAI schema）
    ├── skills/
    │   ├── base.py              # Skill 抽象 + build_skill 分派
    │   ├── prompt_skill.py      # 模板渲染
    │   ├── function_skill.py    # Python 函数执行（受限 builtins）
    │   ├── flow_skill.py        # 多步流程（依赖 FlowRunner 端口）
    │   └── agent_skill.py       # 子 Agent（依赖 SubagentRunner 端口）
    ├── tools/
    │   ├── base.py              # BaseTool / ToolResult
    │   ├── registry.py          # ToolRegistry（V0.1 兼容，可被 PluginRegistry 取代）
    │   ├── mcp.py               # MCP 客户端 + McpTool
    │   ├── http_openapi.py      # OpenAPI→工具 + HttpOpenApiTool
    │   └── builtin/
    │       ├── calculator.py
    │       └── http.py
    ├── memory/
    │   ├── working.py           # Redis Working Brain
    │   ├── consolidator.py      # 规则抽取 + 相似度去重（依赖 LongTermMemory 端口）
    │   └── manager.py           # MemoryManager 门面（组合 Working + LongTerm + Consolidator）
    ├── events/
    │   └── events.py            # RuntimeEvent 数据模型（run.started/step.completed/…）
    └── default/
        ├── litellm_gateway.py   # LiteLLMGateway
        ├── litellm_embedder.py  # LiteLLMEmbedder + HashEmbedder + build_embedder
        └── redis_working.py     # Redis 版 WorkingMemory（或并入 memory/working.py）
```

---

## 3. 核心数据类型

> 以下均为纯数据结构（pydantic / dataclass），不携带任何 IO 依赖。

```python
# ===== 循环内共享状态（原 core/state.py）=====
class PlanStep(TypedDict):
    id: int
    description: str
    status: str                          # pending|running|done|failed

class AgentState(TypedDict, total=False):
    agent_id: str
    run_id: str | None
    session_id: str
    tenant_id: str
    user_id: str | None
    task: str
    messages: list[dict]
    plan: list[PlanStep]
    action: str | None                   # 插件函数名 或 "__finish__"
    action_input: dict | None
    last_tool_result: str | None
    iteration: int
    max_iterations: int
    status: str                          # running|completed|failed
    result: str | None
    error: str | None
    plugins: list[dict]                  # 装配后的插件引用
    memory_ctx: list[dict]               # 召回的长期记忆
    approvals: list[str]                 # 本次 run 已批准的高危资源
    subagent_depth: int
    system_prompt: str | None
    token_usage: dict

# ===== LLM 数据（原 llm/base.py）=====
class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: dict = {}

class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []
    usage: Usage = Usage()

# ===== 记忆数据 =====
class MemoryEntry(BaseModel):
    id: str
    tenant_id: str
    user_id: str | None = None
    session_id: str | None = None
    content: str
    importance: float = 0.5
    confidence: float = 0.5
    source: str = "vector"               # working|vector
    similarity: float | None = None
    created_at: datetime | None = None

# ===== 运行时输入 =====
class RuntimeConfig(BaseModel):
    max_iterations: int = 20
    timeout_seconds: int = 120
    max_subagent_depth: int = 3

class AgentDefinition(BaseModel):
    model: str
    system_prompt: str | None = None
    plugins: list[Plugin] = []           # 业务 DbPluginLoader 装配好的插件
    runtime: RuntimeConfig = RuntimeConfig()

class RunContext(BaseModel):
    tenant_id: str = "default"
    user_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    subagent_depth: int = 0

class Step(BaseModel):
    seq: int
    node: str
    action: str | None = None
    output: dict | None = None
    status: str = "success"
    latency_ms: int | None = None

class RunResult(BaseModel):
    status: str                           # completed|failed
    result: str | None = None
    error: str | None = None
    steps: list[Step] = []
    token_usage: Usage = Usage()
    pending_approvals: list[dict] = []    # 高危插件预检结果（框架计算，业务落库）
```

---

## 4. 能力端口（Ports）

> 端口是框架与业务的**契约（ABI）**。框架调用端口、业务实现端口。全部定义在 `ports.py`。

```python
class LLMGateway(Protocol):
    async def chat(self, messages: list[dict], model: str,
                   tools: list[dict] | None = None) -> LLMResponse: ...

class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class Plugin(Protocol):                   # 原 plugins/base.py
    kind: str
    manifest: PluginManifest
    async def setup(self, config: dict) -> None: ...
    async def invoke(self, ctx: InvokeContext, **kw: Any) -> Any: ...
    async def teardown(self) -> None: ...

class PermissionChecker(Protocol):        # 原 iam/permission_manager.py 的 check()
    def check(self, ctx: PermissionContext, action: str,
              resource_type: str, resource_id: str,
              resource_permission: str = "read",
              requires_approval: bool = False,
              approved: set[str] | None = None) -> PermissionDecision: ...

SubagentRunner = Callable[[str, str, InvokeContext], Awaitable[str]]  # (agent_ref, task, ctx)
FlowRunner      = Callable[[dict, InvokeContext, dict], Awaitable[str]]  # (graph_spec, ctx, kw)

class WorkingMemory(Protocol):            # 原 memory/working.py
    async def get_history(self, session_id: str) -> list[dict]: ...
    async def append(self, session_id: str, message: dict) -> None: ...

class LongTermMemory(Protocol):           # 原 memory/vector.py 的接口
    async def recall(self, db, tenant_id: str, user_id: str | None,
                     query: str, top_k: int = 5) -> list[MemoryEntry]: ...
    async def add(self, db, *, tenant_id: str, user_id: str | None,
                  session_id: str | None, content: str,
                  importance: float = 0.5, confidence: float = 0.5) -> str: ...

class EventSink(Protocol):                # 原 run_agent 的 on_step 回调正式化
    async def __call__(self, event: RuntimeEvent) -> None: ...
```

**注意 `LongTermMemory.recall/add` 的 `db` 参数**：框架不 import 业务 DB，这里把「数据库会话」抽象为调用方传入的透明句柄（`Any`），协议不约束其类型，由业务传入 `AsyncSession`。若需彻底解耦，可将 `db` 封装进一个 `MemoryStore` 实现内部的连接管理（见 §12 决策点）。

---

## 5. 编排入口 AgentRuntime

```python
class AgentRuntime:
    def __init__(self, config: RuntimeConfig | None = None): ...

    async def run(
        self,
        definition: AgentDefinition,
        task: str,
        context: RunContext,
        *,
        history: list[dict] = (),
        memory_context: list[MemoryEntry] = (),
        approvals: list[str] = (),
        deps: RuntimeDeps,
    ) -> RunResult: ...
```

**run() 内部流程**（等价于现有 `build_graph` + `run_agent`，但只回调端口）：

```
1. 组装 PluginRegistry（由 definition.plugins 注册，生成 OpenAI function schema）
2. 构建 AgentState（task/history/memory_ctx/approvals/subagent_depth/…）
3. 编译 LangGraph：plan → decide → execute → observe（条件回边）
4. astream 逐节点驱动：
     - plan/decide 调 deps.llm
     - execute 前调 deps.permission_checker.check()（可缺省=不鉴权）
     - execute 内 invoke 插件；agent-skill 调 deps.subagent_runner
     - 每步产出 Step，回调 deps.event_sink
5. 收敛或异常后，聚合 token_usage、steps，返回 RunResult
```

**RuntimeDeps**（业务注入的端口实现集合）：

```python
@dataclass
class RuntimeDeps:
    llm: LLMGateway
    embedder: Embedder
    permission_checker: PermissionChecker | None = None   # None = 不鉴权（单测/无 IAM 场景）
    working_memory: WorkingMemory | None = None
    long_term_memory: LongTermMemory | None = None
    event_sink: EventSink | None = None                   # None = 不回调（同步直跑）
    subagent_runner: SubagentRunner | None = None
    flow_runner: FlowRunner | None = None
    id_gen: Callable[[str], str] | None = None            # 默认 uuid4().hex；业务可换 ULID
```

---

## 6. 核心循环（core）

### 6.1 图结构（`core/graph.py`）

```
entry(plan) → decide → execute → observe ─(should_continue)─► decide / END
```

`should_continue`：`iteration >= max_iterations` 或 `action == "__finish__"` → `finish`，否则回到 `decide`。

### 6.2 四节点契约

| 节点 | 读 State | 写 State | 依赖端口 |
|------|----------|----------|----------|
| **plan** | task, memory_ctx | plan | `deps.llm` |
| **decide** | plan, messages, last_tool_result, system_prompt | action, action_input, result | `deps.llm`（带工具 schema）|
| **execute** | action, action_input, approvals | last_tool_result | `deps.permission_checker`、插件 invoke、`deps.subagent_runner` |
| **observe** | last_tool_result, iteration | messages, iteration, status, result | — |

### 6.3 execute 节点授权时序

```
插件 = registry.get(action)
① deps.permission_checker.check(ctx, "execute", manifest.kind, manifest.name,
                                 manifest.permission, manifest.requires_approval, approved)
    → DENY            : last_tool_result = "[denied] ..."
    → REQUIRE_APPROVAL: last_tool_result = "[approval required] ..."
    → ALLOW           : 继续
② prompt-skill 注入 memory_ctx 占位符
③ await registry.invoke(action, InvokeContext(...), **action_input)
④ _coerce_result 归一化为字符串
```

---

## 7. 插件体系（plugins）

- **PluginManifest**：`name / version / kind / description / parameters(JSON Schema) / permission(read|write|admin) / requires_approval / dependencies / tags`；`function_name` = 工具用裸名、其他 kind 加 `{kind}_` 前缀防冲突。
- **InvokeContext**：`tenant_id / user_id / run_id / trace_id / session_id / subagent_depth`（横切上下文，跨层透传）。
- **PluginRegistry**：按「裸名 / `kind:name@version` ref / OpenAI function name」三种键索引；提供 `to_openai_schema()`、`invoke(key, ctx, **kw)`。
- **ToolAsPlugin**：把 V0.1 `Tool.run()` 适配为 `Plugin.invoke()`，让工具与技能统一对待。
- **ref 解析**（`manifest.py`）：`kind:name@version`，`@version` 可省。

---

## 8. 技能（skills）

| 形态 | `type` | `body` | invoke 行为 | 依赖端口 |
|------|--------|--------|-------------|----------|
| prompt | `prompt` | `{template}` | 渲染 `{{var}}`，注入 `memory_ctx` | — |
| function | `function` | `{source}` | `exec` 执行 `run()`，受限 builtins（**非沙箱**） | — |
| flow | `flow` | `{graph_spec}` | 交给 `FlowRunner` 执行 | `flow_runner` |
| agent | `agent` | `{agent_ref}` | 交给 `SubagentRunner` 调子 Agent | `subagent_runner` |

> 若 `flow_runner`/`subagent_runner` 未注入，invoke 返回「未接线」提示而非静默失败（现有行为保留）。

---

## 9. 工具（tools）

- `BaseTool`：`id / name / description / permission / parameters` + `run(**kw) -> ToolResult`。
- `McpClient` + `McpTool`：MCP streamable HTTP（JSON-RPC 2.0），`endpoint` + `config.auth.headers`。
- `HttpOpenApiTool` + 辅助函数：OpenAPI spec → 生成 JSON Schema → 构造带 URL 模板的 HTTP 调用；支持 `api_key` 鉴权、path/query 参数分离。
- `builtin/`：calculator（AST 白名单求值）、http（GET/POST）。

---

## 10. 记忆（memory）

- **WorkingMemory**（短期）：Redis `wb:{session_id}:messages`，滑动窗口 + TTL。
- **LongTermMemory**（长期）：语义写入 + top-k 召回，相似度 SQL 侧 `cosine_distance` 计算，读取不选 embedding 列。
- **Consolidator**：规则抽取（user 陈述 + 最终 assistant 回答）→ 相似度去重（阈值 0.85）→ 写 LongTermMemory。
- **MemoryManager**：门面，组合三者，对 runtime 暴露 `write/recall/consolidate`。

> V0.3 将在此层扩展 Memory Graph、`reflect` 评分、遗忘、`sufficiency`（见《技术方案设计.md》4.3）。

---

## 11. 事件（events）

`RuntimeEvent`（纯数据，无传输）：

```
run.started / step.completed / run.completed / run.failed
run.awaiting_human / run.approved / run.rejected
```

每条含 `run_id` + 可选 `trace_id` + 时间戳。**序列化为 SSE 是业务层 `EventSink` 实现的事**，框架只产出事件对象。

---

## 12. 默认实现（default）

| 端口 | 默认实现 | 备注 |
|------|----------|------|
| `LLMGateway` | `LiteLLMGateway` | 单厂商，读 `api_key`/`api_base` |
| `Embedder` | `LiteLLMEmbedder`（有 key）/ `HashEmbedder`（无 key 离线回退） | 维度固定 1536 |
| `WorkingMemory` | Redis 版 | 需外部注入 Redis 连接 |

---

## 13. 与业务层的契约与禁止事项

**契约（业务必须提供）**：实现 §4 端口并通过 `RuntimeDeps` 注入；调用 `AgentRuntime.run()` 时提供 `AgentDefinition`（含装配好的插件）。

**禁止事项**：
- 框架禁止 import `smartagent.api` / `smartagent.db` / `smartagent.config` / `fastapi`。
- 框架禁止直接读写 PostgreSQL/Redis 之外的业务存储（Redis Working Brain 是唯一例外，且经端口）。
- 框架禁止在 `check()` 里做 DB 查询（RBAC/Grant 数据由业务预加载进 `PermissionContext`）。

---

## 14. 从现有代码迁移映射

| 现文件（src/smartagent/） | 迁移目标 | 动作 |
|---------------------------|----------|------|
| `core/state.py` | `agent-core/state.py` | 移动 |
| `core/graph.py` + `core/nodes/*` | `agent-core/core/*` | 移动，`iam` 依赖改为 `PermissionChecker` 端口 |
| `llm/base.py` `llm/embedder.py` | `agent-core/ports.py`（协议）+ `default/`（实现） | 拆协议/实现 |
| `llm/litellm_gateway.py` | `agent-core/default/litellm_gateway.py` | 移动 |
| `plugins/base.py` `registry.py` `manifest.py` | `agent-core/plugins/*` | 移动 |
| `plugins/loader.py` | **业务** `adapters/db_plugin_loader.py` | 拆出 DB 读取；纯「引用解析」留框架 |
| `skills/*` | `agent-core/skills/*` | 移动（回调已注入，天然解耦）|
| `tools/*`（含 builtin） | `agent-core/tools/*` | 移动 |
| `memory/working.py` `consolidator.py` `manager.py` | `agent-core/memory/*` | 移动 |
| `memory/vector.py` | `agent-core/ports.py`（`LongTermMemory` 协议） | 实现下沉业务 `adapters/pgvector_memory.py` |
| `iam/permission_manager.py` | 框架 `ports.py`（`PermissionChecker`+`check()` 纯逻辑） | `build_context()` 留业务 |
| `events/sse.py` | `agent-core/events/events.py`（事件模型） | SSE 序列化留业务 |
| `config.py` | 框架 `RuntimeConfig` + 业务 `AppConfig` | 拆分 |

---

> 本文档是框架层的「契约文档」。业务层如何实现这些端口、如何装配 RuntimeDeps、如何暴露 HTTP，见 **《业务层详细设计.md》**。
