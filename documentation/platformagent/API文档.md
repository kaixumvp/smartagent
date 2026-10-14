# PlatformAgent API 文档

> 在线 OpenAPI/Scalar 是接口 schema 与参数的权威来源：运行后访问 `GET /docs`；健康检查为 `GET /health`。
> 本页概述当前 API 分组与交互约束，不替代运行时生成的 OpenAPI。

## 1. 基本约定

- 业务 API 默认挂在 `/v1` 下。
- 鉴权使用 `Authorization: Bearer <token>`；用户与资源按 tenant 隔离。
- 跨租户资源按 404 处理，避免泄露资源是否存在。
- 错误响应包含 `error.code`、`error.message` 和可用时的 `trace_id`。
- 带 `stream: true` 的 Run 请求使用 SSE；RunStep 事件在持久化后再推送。
- Capability Registry 的服务间 API 由平台后端代理；集成密钥不发给浏览器。

## 2. 路由分组

| 路由模块 | 主要能力 |
|---|---|
| `auth` | 登录、密码变更 |
| `users` | 用户创建、查询、更新、密码管理 |
| `roles` / `grants` | RBAC 角色权限与资源授权 |
| `agents` | Agent CRUD、版本管理、运行历史 |
| `runs` | 启动/查询/删除 Run、SSE、HITL approve/reject |
| `tools` / `skills` | 租户级 Tool、Skill 管理 |
| `memory` | 长期记忆召回调试接口 |
| `golden_sets` / `evaluations` / `feedback` | Golden Set、异步离线评测、Run 反馈 |
| `experiments` | 实验、状态切换、结果查询 |
| `cost` | 成本汇总与缓存统计 |
| `capability` | Capability Provider 与 Tool 目录的服务端代理读取 |

后端当前注册 15 个路由模块，路径和 operation 数会随 schema 变化；执行环境的 OpenAPI (`/openapi.json`)
是具体路径的准确信息。启动及鉴权配置参见[后端 README](../../application/platformagent/backend/README.md)。

## 3. Run 生命周期

创建入口：

```http
POST /v1/agents/{agent_id}/runs
```

请求可以携带 `input`、`conversation_id` 及 `stream`；非流式返回 Run 结果，流式返回 SSE 事件。
支持的 HITL 决策入口：

```http
POST /v1/runs/{run_id}/actions
```

该 action 用于处于 `awaiting_human` 状态的运行；批准后在同一 Run 上经 checkpoint 恢复。
当前不存在独立的用户 pause、resume、cancel HTTP 控制端点；HITL 的 approve/reject 不是通用运行控制 API。

## 4. 评测与成本

- Golden Set 管理用于保存离线评测用例。
- Evaluation 创建为异步任务并通过查询端点读取进度和结果。
- Run feedback 记录在线反馈。
- Experiment 分配固定变体并提供结果汇总。
- Run 输出包含 token usage、实际 model 与 cost（版本和字段详见运行时 OpenAPI）。

## 5. SSE 事件

当前 Run 事件以 `run.started`、`step.completed` 及终态事件为主，终态包括 `run.completed`、`run.failed`、
`run.awaiting_human`。SSE 细节由框架事件和业务层序列化器共同决定；请以 `smartagent.api.sse` 与当前 OpenAPI
为准。不存在 WebSocket API 的当前实现。
