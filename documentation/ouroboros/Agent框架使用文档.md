# Ouroboros Agent 框架使用文档

本文面向使用 Ouroboros 的宿主开发者。Python 安装约束及所有可选能力见
[项目 README](../../application/ouroboros/README.md) 与 [`pyproject.toml`](../../application/ouroboros/pyproject.toml)。

## 1. 适用边界

Ouroboros 提供 Agent 循环、插件协议、工具/技能执行和运行时端口；宿主负责 HTTP、身份、租户、持久化、
密钥、业务授权上下文与外部服务的装配。框架不会替宿主创建数据库或配置 Web 服务。

框架当前版本为 2.0.0，公开导入包名为 `ouroboros`，不再使用 `src`。

## 2. 运行 Agent 的最小结构

一次运行由三部分组成：

- `AgentDefinition`：Agent 的模型、系统提示、插件和 `RuntimeConfig`。
- `RunContext`：run/session/user/tenant 等本次运行上下文。
- `RuntimeDeps`：LLM 必需依赖，以及按需注入的 permission checker、memory、event sink、checkpointer、
  subagent runner、tracer、metrics 等端口。

框架在 `AgentRuntime.run(definition, task, context, deps)` 中执行运行循环，返回强类型 `RunResult`；
可恢复运行使用 `AgentRuntime.resume(...)` 与宿主 checkpoint。

```python
from ouroboros.core.runtime import (
    AgentDefinition,
    AgentRuntime,
    RunContext,
    RuntimeDeps,
)
from ouroboros.llm.litellm_gateway import LiteLLMGateway

definition = AgentDefinition(
    model="your-model",
    system_prompt="You are a helpful assistant.",
)
deps = RuntimeDeps(llm=LiteLLMGateway(model="your-model", api_key="..."))
result = await AgentRuntime().run(
    definition,
    "Summarize the request",
    RunContext(run_id="run_demo", session_id="session_demo"),
    deps,
)
```

生产环境的密钥应由宿主配置系统注入，不应写入示例代码、日志或浏览器。

## 3. 插件与技能

1. 将 Tool 或 Skill 注册到 `PluginRegistry`。
2. 用 `SkillManager` 按宿主保存的配置构造 Skill。
3. 把所需插件交给 `AgentDefinition.plugins`。
4. 将宿主授权检查器注入 `RuntimeDeps.permission_checker`。

支持的 Skill 形态包括 prompt、function、flow 和 agent。Tool/Skill 需要提供可供模型调用的 schema；
execute 节点会在调用前通过注入的权限端口检查。

结构图见 [Plugin / Tool / Skill UML](./plugins-tools-skills-uml.md)。

## 4. 宿主端口与运行责任

| 端口 | 宿主通常提供 |
|---|---|
| `LLMGateway` | 模型供应商、密钥、路由和账单 |
| `PermissionChecker` | 用户/租户权限数据加载与审计 |
| `WorkingMemory` / `LongTermMemory` | 会话历史和长期记忆存储 |
| `Knowledge` / `Retriever` | 外部知识摄取与检索后端 |
| `EventSink` | step/run 落库和 SSE/WebSocket 分发 |
| `Checkpointer` | 进程间可持久化的 checkpoint |
| `SubagentRunner` | 子 Agent 的业务上下文与隔离 session |

协议定义集中于 `ouroboros.ports`。宿主可组合框架公开的 registry、gateway、memory 等模块，但不要依赖
`core` 内部节点和 state 结构作为自己的持久化格式。

## 5. 相关资料

- [Agent 框架详细设计](./Agent框架层详细设计.md)
- [框架版本规划](./版本规划.md)
- [业务层接入约束](../platformagent/业务层详细设计.md)
- [Ouroboros README](../../application/ouroboros/README.md)
