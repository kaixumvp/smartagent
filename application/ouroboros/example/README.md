# Ouroboros 示例

每个文件对应一个模块/能力，展示「如何单独使用」以及「如何经 `RuntimeDeps` 配合 Agent 运行」。所有示例默认**离线运行**（用 `_shared.ScriptedLLM` 脚本化 Mock，无需真实 API key）。

## 运行方式

```bash
# 先安装（poetry 环境下 ouroboros 已可导入）
poetry install
poetry run python example/first_example.py

# 或在未安装时指定源码路径
PYTHONPATH=src python example/first_example.py
```

要接真实模型，设置环境变量后改用 `_shared.real_llm()`：

```bash
export OUROBOROS_API_KEY=sk-...   # 或 DEEPSEEK_API_KEY
export OUROBOROS_MODEL=deepseek/deepseek-chat
```

## 清单

| 文件 | 模块/能力 | 说明 |
|------|-----------|------|
| `first_example.py` | 最小闭环 | `AgentRuntime.run` 跑一个带工具调用的 Agent |
| `plugins_tools.py` | 插件 / 工具 | 自定义 `BaseTool`、完整 `Plugin`、`PluginRegistry`、`ToolAsPlugin` |
| `skills_example.py` | 技能 | 四形态 Skill（prompt/function/flow/agent）+ `SkillManager` |
| `memory.py` | 记忆 | Working / LongTerm / Consolidator / Reflector / MemoryManager |
| `knowledge.py` | 知识 | `Knowledge`/`Retriever` 端口 + `KnowledgePlugin` + 知识回退 |
| `permissions_hitl.py` | 权限 / HITL | `check_permission` + 高危暂停 → `resume` 续跑（checkpoint） |
| `events_streaming.py` | 事件 / 流式 | `EventSink` 端口 + `RuntimeEvent` + 宿主侧 SSE 序列化 |
| `reliability.py` | 可靠性 | Retry / 熔断 / 超时 / 子 Agent 深度 |
| `ports_example.py` | 端口全景 | 实现并注入全部契约，一次接线跑完整 Agent |
| `replay.py` | 确定性重放 | `RecordingGateway` / `ReplayGateway`，同一 run 可离线复现 |
| `evaluation.py` | 离线评测 | `GoldenSet` + `Judge` + `run_evaluation` |
| `cost.py` | 成本感知 | `CachingGateway` / `TieredRouter` / `TokenBudget` + 预算中止 |
| `_shared.py` | 公共工具 | `ScriptedLLM` + `real_llm()`（示例间复用，非 API） |

## 与 Agent 配合的关键入口

- **注入端口**：`RuntimeDeps(llm=..., permission_checker=..., long_term_memory=..., knowledge=..., event_sink=..., checkpointer=..., subagent_runner=..., flow_runner=..., retry=...)`
- **装配插件**：`AgentDefinition(model=..., system_prompt=..., plugins=registry.all())`
- **驱动运行**：`AgentRuntime().run(definition, task, RunContext(...), deps)` → `RunResult`
- **暂停恢复**：`AgentRuntime().resume(definition, run_id, approvals, deps)`（需 `checkpointer`）
