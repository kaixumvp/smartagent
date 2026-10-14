# Changelog

本文件按 [SemVer](https://semver.org/) 记录 Ouroboros 的变更。v1.0 起：破坏性变更只出现在 major，弃用至少跨一个 minor。

## [2.0.0] - 2026-10-10

### 变更（破坏性）
- **导入包名 `src` → `ouroboros`**：发行包 `ouroboros` 此前导出的顶层包字面就叫 `src`，
  与宿主自己的 src-layout 直接冲突，也与本文件 v1.0 段声明的公共 API 面（「顶层 `ouroboros`」）
  从未一致过。所有 `from src.x import y` 改为 `from ouroboros.x import y`。
  公共 API 面的**符号**未变，`__all__` 无改动，仅包名前缀变化。

  受影响的导入写法（逐一替换即可）：

  | 旧 | 新 |
  |---|---|
  | `from src import AgentRuntime` | `from ouroboros import AgentRuntime` |
  | `from src.ports import LLMGateway` | `from ouroboros.ports import LLMGateway` |
  | `from src.core.runtime import AgentDefinition` | `from ouroboros.core.runtime import AgentDefinition` |
  | `from src.tools.registry import build_default_registry` | `from ouroboros.tools.registry import build_default_registry` |

  日志命名空间同步从 `src` 改为 `ouroboros`（`logging.getLogger("ouroboros")`）。

### 移除
- `langgraph` 依赖。核心循环自 v0.3 起就是 `core/runtime.py` 里的手写状态机，
  `build_graph`/`run_agent` 在 v1.0.0 已删除，该依赖自那时起就无人 import。
  连带移除了 `langgraph` / `langgraph-checkpoint` / `langgraph-prebuilt` / `langgraph-sdk` /
  `langchain-core` / `langchain-protocol` / `xxhash` / `ormsgpack` 共 8 个传递依赖。

## [1.1.0] - 2026-08-26

### 新增
- **确定性重放**：`RecordingGateway` / `ReplayGateway` / `dump_recording` / `load_recording`（`llm/replay.py`），同一 run 可离线复现。
- **评测端口**：`Judge` / `JudgeVerdict` 端口（`ports.py`）+ `Case` / `GoldenSet` / `run_evaluation` / `HeuristicJudge`（`evaluation/`）。
- **成本感知**：`CachingGateway`（prompt 缓存复用）、`TieredRouter` + `message_length_classifier`（模型分级路由）、`TokenBudget`（token 预算）。
- `RuntimeConfig.max_total_tokens`：运行期 token 预算，超限中止（`status="failed"`）。

## [1.0.0] - 2026-08-26

### 移除（破坏性）
- 删除 `build_graph` / `run_agent` deprecated shim（`core/graph.py`），请改用 `AgentRuntime`。

### 新增
- `py.typed` 标记，类型完备（PEP 561）。
- 公共 API 面冻结：顶层 `ouroboros` 与各子包 `__all__` 显式导出。
- 兼容矩阵：Python 3.11 – 3.14。

## [0.4.0] - 2026-08-26

### 新增
- 可观测：`observability/`（`Tracer` 可选依赖 `opentelemetry-api` + `Metrics` 端口），`trace_id` 经 `InvokeContext` 透传。
- 安全：`FunctionSkill` 默认子进程沙箱；`security/`（注入边界标注 + `Redactor` 脱敏）。
- 韧性：`FallbackLLMGateway` + `FaultTolerantGateway`（`llm/routing.py`）。
- 并发：单轮多 `tool_calls` 并行执行。

## [0.3.0] - 2026-08-26

### 新增
- 端口收口：全部框架↔宿主契约集中到 `ports.py`。
- `AgentRuntime` 门面 + 强类型（`AgentDefinition` / `RunContext` / `RuntimeConfig` / `RuntimeDeps` / `Step` / `RunResult`）。
- 可靠执行：`RetryPolicy` + `CircuitBreaker`、超时、子 Agent 深度、checkpoint 暂停/恢复。
- 事件解耦：`RuntimeEvent` + `EventSink`。
- 知识端口：`Knowledge` / `Retriever` + `KnowledgePlugin`；记忆 `reflect` / 遗忘 / 充分性。

## [0.2.0] - 2026-08-24

### 新增
- 插件协议、四形态 Skill、MCP/HTTP 工具、记忆（Working/Consolidator）、授权、事件；从平台单体独立成包。

## [0.1.0]

### 新增
- 运行循环 + Builtin 工具 + LLM 网关。
