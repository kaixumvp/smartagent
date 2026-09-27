# Changelog

本文件按 [SemVer](https://semver.org/) 记录 Ouroboros 的变更。v1.0 起：破坏性变更只出现在 major，弃用至少跨一个 minor。

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
