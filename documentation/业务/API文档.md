# SmartAgent HTTP API 文档

> 业务层对外暴露的 REST/SSE 接口。交互式文档（Scalar）已在运行时提供，见 `GET /docs`；本文为 Markdown 参考。
> 设计见 **《业务层详细设计.md》**。

---

## 1. 概述

| 项 | 值 |
|----|-----|
| Base URL | `http://<host>:8000` |
| 前缀 | `/v1` |
| 认证 | JWT Bearer（`Authorization: Bearer <token>`）|
| 免鉴权 | `GET /health`、`POST /v1/auth/login` |
| 内容类型 | `application/json` |
| 流式 | `POST /v1/agents/{id}/runs` 传 `stream: true` 返回 `text/event-stream` |

**统一错误格式**（非 2xx）：

```jsonc
{ "error": { "code": "PERMISSION_DENIED", "message": "...", "trace_id": "trace_..." } }
```

响应头始终回传 `X-Trace-Id`（可自带上行 `X-Trace-Id` 关联全链路）。

---

## 2. 认证

### `POST /v1/auth/login`

```jsonc
// 请求（tenant 可选）
{ "username": "admin", "password": "******", "tenant": "default" }
// 响应 200
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600 }
```

> 用户名**仅在租户内唯一**。省略 `tenant` 时按用户名全局查找；若该用户名在多个租户下存在，返回 401 并提示需指定 `tenant`（不会静默取第一条）。单租户部署可继续省略该字段。
> 登录成功与失败均写入 `audit_logs`（`action=auth.login`）。

### `POST /v1/auth/change-password`　·　登录即可

```jsonc
{ "current_password": "旧密码", "new_password": "新密码至少8位" }
// 204 No Content
```

**必须校验当前密码**——光有合法 token 不足以改密，这样被盗的 token 无法用来永久接管账号。改别人的密码走 `POST /v1/users/{id}/password`（需 `user:manage`）。

### 首次部署：账号从哪来

**没有自助注册**，这是刻意的：多租户平台里账号只有在租户内、附带角色与资源授权才有意义，开放匿名注册需要额外引入邮箱验证、防滥注、租户归属判定，与形态不符。

引导流程：

```
alembic upgrade head        # 种下 tenant=default + 用户 admin（角色 admin）
  └─ 密码取自环境变量 BOOTSTRAP_ADMIN_PASSWORD；未设置则回落 admin123 并打印警告
POST /v1/auth/login         # 用 admin 登录
POST /v1/auth/change-password   # 立即轮换（若用了回落密码）
POST /v1/users              # 建其余账号
```

---

## 2.1 Users（用户管理）

守卫用 `user:manage` 而非 admin 角色：`require_permission` 内部对 admin 短路，因此**管理员照常通过**，同时用户管理可委派给持有该权限码的非 admin 角色。所有操作严格限于**调用方所在租户**，跨租户一律 404（不是 403——403 会泄露账号是否存在）。

### `POST /v1/users`　·　需权限 `user:manage`

```jsonc
// 请求（roles 传角色**名**，在本租户内解析）
{ "username": "alice", "password": "至少8位", "name": "Alice", "roles": ["operator"] }
// 响应 201
{ "id": "user_...", "tenant_id": "default", "username": "alice", "name": "Alice",
  "status": "active", "roles": ["operator"], "created_at": "..." }
```

- 响应**绝不包含** `password_hash`；密码以 PBKDF2-HMAC-SHA256（200k 迭代）存储
- 同租户重名 → 409
- 角色名无法解析 → 400 并列出无法解析的名字（不静默忽略，否则会建出权限比预期少的账号而毫无提示）

### `GET /v1/users` / `GET /v1/users/{id}`　·　需权限 `user:manage`

返回本租户用户（含 `roles`，不含密码哈希）。

### `PATCH /v1/users/{id}`　·　需权限 `user:manage`

```jsonc
{ "status": "disabled" }        // active | disabled
{ "roles": ["viewer"] }         // 覆盖式重设整个角色集合，不是追加
```

被禁用的用户无法登录（`login` 按 `status=active` 过滤）。**不允许禁用自己**（400）——没有第二个管理员时会把自己永久锁在系统外。

### `POST /v1/users/{id}/password`　·　需权限 `user:manage`

```jsonc
{ "new_password": "至少8位" }
```

管理员重置，**无需当前密码**。系统内没有邮件体系，这是「忘记密码」的唯一出路。

---

## 3. Agents

### `POST /v1/agents`　·　需权限 `agent:create`

```jsonc
// 请求
{
  "name": "客服助手",
  "version": "1",
  "config": {
    "system_prompt": "你是客服助手",
    "model": "deepseek-chat",
    "plugins": [
      {"type": "skill", "ref": "skill:refund_policy@1.0.0"},
      {"type": "tool",  "ref": "tool:order_query"}
    ],
    "runtime": { "max_iterations": 20 }
  }
}
// 响应 201
{
  "id": "agent_...", "tenant_id": "default", "name": "客服助手",
  "version": "1", "status": "active", "config": { "...": "..." }
}
```

> `config.plugins` 为 V0.2 装配方式；旧版 `config.tools` 数组仍兼容（按 tool 引用处理）。
>
> **版本化（V1.1）**：同名重复 POST 表示发布该逻辑 Agent 的新版本，新版本自动成为 `is_latest`、旧版本清零；同名同版本返回 409。A/B 实验就是在这些版本之间做对比。
> **`config.model` 的取舍**：配了就锁定该模型；**不配**则交给网关决策——开启分级路由时按任务复杂度选廉价/昂贵档，否则用部署默认模型。

### `GET /v1/agents`

返回 `list[AgentOut]`（当前租户）。

### `GET /v1/agents/{agent_id}`

返回单个 `AgentOut`；跨租户或不存在返回 404。

---

## 4. Runs

### `POST /v1/agents/{agent_id}/runs`　·　需权限 `run:execute`

```jsonc
// 请求
{ "input": "帮我算 3*8 再加 100", "stream": false, "user_id": "u_1" }
```

**同步响应 200**（`stream: false`，默认）：

```jsonc
{
  "run_id": "run_...",
  "agent_id": "agent_...",
  "status": "completed",            // running|completed|failed|awaiting_human|canceled
  "result": "3*8+100 = 124",
  "steps": [
    {"seq": 1, "node": "plan",    "output": {"plan": ["计算 3*8", "加 100"]}},
    {"seq": 2, "node": "decide",  "output": {"action": "calculator", "action_input": {"expression": "3*8+100"}}},
    {"seq": 3, "node": "execute", "output": {"result": "124"}},
    {"seq": 4, "node": "observe", "output": {"result": "3*8+100 = 124"}}
  ],
  "usage": {"prompt_tokens": 320, "completion_tokens": 88, "total_tokens": 408},
  "pending_approvals": [],
  "created_at": "2026-08-22T10:00:00Z",
  "finished_at": "2026-08-22T10:00:03Z"
}
```

**高危审批（运行中暂停）**：run 正常执行，直到 `execute` 节点**真正要调用**某个高危资源且授权判定为「需审批」时才暂停。此前的步骤已完成并落库：

```jsonc
{
  "run_id": "run_...", "agent_id": "agent_...", "status": "awaiting_human",
  "result": null,
  "steps": [
    {"seq": 1, "node": "plan",    "output": {"plan": ["删除账号 u42"]}, "status": "success"},
    {"seq": 2, "node": "decide",  "action": "delete_account", "status": "success"},
    {"seq": 3, "node": "execute", "action": "delete_account", "status": "awaiting_human"}
  ],
  "pending_approvals": [{"resource_type": "tool", "resource_id": "delete_account"}]
}
```

> **何时会触发审批**（框架 `check_permission` 语义，容易踩空）：
> - **admin 主体直接放行，永不触发审批**；`auth_enabled=false` 的开发态返回的正是 admin 主体，同样不会触发。
> - 非 admin 主体除了 `run:execute` 功能权限外，还必须对该资源有 `effect=allow` 的 Grant；**没有 Grant 是 `deny`（运行中拒绝并写审计），而不是待审批**。
> - 满足上述条件且资源 `permission=admin` 或 `requires_approval=true` 时，才进入 `awaiting_human`。

**流式**（`stream: true`）：返回 SSE 事件流（见 §11）。暂停时以 `run.awaiting_human` 收尾。

### `GET /v1/runs/{run_id}`

返回 `RunOut`，结构与创建响应一致（`status` 可能为 `running`，此时 `result` 为 null）。

### `POST /v1/runs/{run_id}/actions`　·　需权限 `run:execute`

```jsonc
// 请求（approve 单个资源，或 approve 全部 / reject）
{ "action": "approve", "resource_type": "tool", "resource_id": "delete_account" }
// 或
{ "action": "approve" }      // 批准当前全部待审批资源
// 或
{ "action": "reject" }       // run 置 canceled
// 响应 200：RunOut
```

**approve 后从暂停处续跑**，不重放已完成的步骤——`plan`/`decide` 不会再执行一次，只有被卡住的 `execute` 会用新授权重跑。`seq` 在整个 run 内连续单调：

```jsonc
{
  "run_id": "run_...",            // 与暂停时同一个 run
  "status": "completed",
  "result": "账号 u42 已删除",
  "steps": [
    {"seq": 1, "node": "plan",    "status": "success"},
    {"seq": 2, "node": "decide",  "status": "success"},
    {"seq": 3, "node": "execute", "status": "awaiting_human"},   // 暂停的那一步，保留在时间线上
    {"seq": 4, "node": "execute", "status": "success"},          // 审批后重跑
    {"seq": 5, "node": "observe", "status": "success"},
    {"seq": 6, "node": "decide",  "status": "success"}
  ],
  "pending_approvals": []
}
```

- 若还有其他资源待审批，响应仍为 `status=awaiting_human`，`pending_approvals` 为剩余项。
- 对**非** `awaiting_human` 状态的 run 提交审批 → 409 `INVALID_STATE`。
- `approve` / `reject` 决策均写入 `audit_logs`。

---

## 5. Tools

### `GET /v1/tools`

返回 `list[ToolOut]`（内置工具 + 本租户的 mcp/http 工具）。

```jsonc
[{ "id": "tool_calculator", "name": "calculator", "type": "builtin",
   "description": "...", "parameters": {...}, "permission": "read", "requires_approval": false }]
```

### `POST /v1/tools`　·　需权限 `tool:register`

```jsonc
// MCP 工具
{
  "name": "github", "type": "mcp",
  "description": "GitHub 操作",
  "endpoint": "https://mcp.example.com/github",
  "config": { "auth": {"type": "bearer", "token_env": "GITHUB_MCP_TOKEN"} },
  "permission": "write", "requires_approval": true
}
// HTTP(OpenAPI) 工具
{
  "name": "order_query", "type": "http",
  "description": "订单查询",
  "endpoint": "https://openapi.example.com/orders.yaml",
  "config": { "auth": {"type": "api_key", "header": "X-Api-Key", "key_env": "ORDER_API_KEY"} },
  "permission": "read", "requires_approval": false
}
// 响应 201：ToolOut
```

> `type` 枚举：`builtin | mcp | http`。

---

## 6. Skills

### `POST /v1/skills`　·　需权限 `skill:register`

```jsonc
// prompt-skill
{
  "name": "refund_policy", "version": "1.0.0", "type": "prompt",
  "description": "退款政策",
  "body": { "template": "退款政策：7 天无理由（上下文：{{memory_ctx}}）" },
  "permission": "read", "requires_approval": false, "tags": []
}
// agent-skill（子 Agent）
{
  "name": "ticket_escalation", "version": "1.0.0", "type": "agent",
  "description": "工单升级",
  "body": { "agent_ref": "agent_escalation_v1" },
  "permission": "admin", "requires_approval": true
}
// 响应 201
{ "id": "skill_...", "tenant_id": "default", "name": "refund_policy",
  "version": "1.0.0", "type": "prompt", "is_latest": true, "status": "active" }
```

> 同名新版本写入即自动成为 `is_latest`；`type` 枚举：`prompt | function | flow | agent`。

### `GET /v1/skills` / `GET /v1/skills/{skill_id}`

返回 `list[SkillOut]` / `SkillOut`。

---

## 7. Roles

### `POST /v1/roles`　·　需 admin

```jsonc
{ "name": "数据分析组", "permission_codes": ["run:execute", "run:view"] }
// 响应 201
{ "id": "role_...", "tenant_id": "default", "name": "数据分析组", "is_builtin": false }
```

### `POST /v1/roles/{role_id}/permissions`　·　需 admin

```jsonc
{ "permission_codes": ["run:execute", "agent:view"] }   // 覆盖式绑定
```

### `GET /v1/roles`

返回 `list[RoleOut]`。

---

## 8. Grants（资源级授权）

### `POST /v1/grants`　·　需 admin

```jsonc
{
  "principal_type": "user",          // user | role
  "principal_id": "u_1",
  "resource_type": "tool",           // tool | skill | agent | knowledge
  "resource_id": "tool_db_query",
  "action": "execute",
  "effect": "allow"                  // allow | deny
}
// 响应 201：GrantOut
```

### `GET /v1/grants?principal_id=u_1`

返回 `list[GrantOut]`（当前租户，可按 `principal_id` 过滤）。

### `DELETE /v1/grants/{grant_id}`　·　需 admin

返回 204。

---

## 9. Memory

### `POST /v1/memory/recall`

```jsonc
// 请求
{ "query": "用户偏好", "user_id": "u_1", "top_k": 5 }
// 响应 200
[
  { "id": "mem_...", "content": "用户偏好简洁回答",
    "similarity": 0.93, "importance": 0.5, "confidence": 0.5 }
]
```

> 调试/评估用的长期记忆召回接口。

---

## 9.1 Evaluation（V1.1）

### `POST /v1/golden-sets`　·　需权限 `eval:manage`

```jsonc
{
  "name": "客服回归集", "description": "发布前必过",
  "cases": [
    { "task": "退款政策是几天？", "reference": "7 天" },
    { "task": "怎么联系人工？", "reference": null }   // 无参考答案时按相关性打分
  ]
}
// 响应 201：GoldenSetOut（含 cases）
```

`GET /v1/golden-sets` 返回列表（**不含 cases**）；`GET /v1/golden-sets/{id}` 返回单个（含 cases）。

### `POST /v1/evaluations`　·　需权限 `eval:manage`

```jsonc
// 请求
{ "golden_set_id": "gset_...", "agent_id": "agent_...", "judge_type": "llm" }
// 响应 202（立刻返回，不等评测跑完）
{ "id": "eval_...", "status": "queued", "total": 0, "results": [] }
```

一个评测集是 N 次完整 Agent 运行，因此**异步执行 + 轮询**。`judge_type` 取 `llm`（默认，用 `judge_model`）或 `heuristic`（字符串包含，无 LLM 成本）。

### `GET /v1/evaluations/{id}`　·　需权限 `eval:view`

```jsonc
{
  "id": "eval_...", "status": "completed",     // queued|running|completed|failed
  "total": 2, "passed": 1, "failed": 1, "avg_score": 0.5, "cost": 0.0031,
  "results": [
    { "case_id": "gcase_0", "run_id": "run_...", "output": "7 天无理由",
      "score": 1.0, "passed": true, "reason": "reference matched", "cost": 0.0016 }
  ]
}
```

> 每个 case 都有独立的 `run_id`，可用 `GET /v1/runs/{run_id}` 下钻完整步骤。
> **重启会中断评测**：任务在进程内运行，服务重启后滞留任务被判 `failed`，`error` 为 `interrupted by a process restart`。
> 评测运行**不写入长期记忆**，避免合成流量污染真实用户的召回。

### `POST /v1/runs/{run_id}/feedback`　·　登录即可

```jsonc
{ "rating": 1, "comment": "答得准", "tags": ["accurate"] }   // rating 标度由调用方约定
// 响应 201：FeedbackOut
```

`GET /v1/runs/{run_id}/feedback` 返回该 run 的全部反馈。

---

## 9.2 Experiments（灰度 A/B，V1.1）

### `POST /v1/experiments`　·　需权限 `experiment:manage`

```jsonc
{
  "name": "客服提示词灰度",
  "entry_agent_id": "agent_v1",          // 客户端照常调这个 Agent
  "variants": [
    { "label": "control", "agent_id": "agent_v1", "weight": 90 },
    { "label": "candidate", "agent_id": "agent_v2", "weight": 10 }
  ],
  "sticky_key": "user"
}
// 响应 201：ExperimentOut（status=draft）
```

`POST /v1/experiments/{id}/status` 传 `{"action":"start"|"stop"}` 启停。

> **权重一旦开跑就冻结**：改权重会移动分桶边界，已分配的用户会静默换组。要改配比就新建实验——因此已 `stopped` 的实验不允许重启（409）。

**分流语义**：实验 `running` 时，`POST /v1/agents/{entry_agent_id}/runs` 会被路由到该调用方所属变体的 Agent，响应里的 `agent_id` 是**实际执行的变体**。分配确定且粘性：同一 `(experiment, subject)` 恒定落同一变体。`subject` 依次取 `body.user_id` → JWT 主体 → run id；**取到 run id 时退化为按次随机、无粘性**，匿名调用需注意。

### `GET /v1/experiments/{id}/results`　·　需权限 `experiment:view`

```jsonc
{
  "experiment_id": "exp_...", "status": "running",
  "variants": [
    { "variant": "control", "agent_id": "agent_v1", "runs": 900, "completed": 890, "failed": 10,
      "avg_cost": 0.0021, "avg_latency_ms": 1830.5, "feedback_count": 120, "avg_rating": 0.82 }
  ]
}
```

---

## 9.3 Cost（V1.1）

### `GET /v1/cost/summary?group_by=agent`　·　需权限 `run:view`

`group_by` 取 `agent` | `model` | `experiment`。

```jsonc
{ "group_by": "model", "total_cost": 12.84, "total_runs": 5120,
  "buckets": [ { "key": "gpt-4o", "runs": 300, "total_cost": 9.1, "total_tokens": 1200000 } ] }
```

> `runs.cost` 从 V1.1 起才有值：该列自 V0.1 就存在，但此前无人写入，**早于本版的运行一律显示 0**。
> 未在价表中的模型按 0 计并记 warning——缺价格显式为 0，好过用错价格。

### `GET /v1/cost/cache`　·　需权限 `run:view`

```jsonc
{ "enabled": true, "hits": 412, "misses": 1088, "hit_rate": 0.2747, "size": 256 }
```

> 缓存是**进程内**的，多 worker 部署时这是单个 worker 的数字，不是全局。

---

## 10. 健康检查

### `GET /health`

```jsonc
{ "status": "ok" }
```

---

## 11. SSE 流式事件

`POST /v1/agents/{id}/runs` 传 `stream: true` 时，响应为 `text/event-stream`，事件序列：

```
event: run.started
data: {"run_id":"run_...","status":"running"}

event: step.completed
data: {"seq":3,"node":"execute","action":"calculator","output":{"result":"124"},"latency_ms":120}

event: run.completed
data: {"run_id":"run_...","status":"completed","result":"124","usage":{...}}

（失败时）
event: run.failed
data: {"run_id":"run_...","status":"failed","error":"..."}

（命中高危审批时，流以此收尾）
event: run.awaiting_human
data: {"run_id":"run_...","status":"awaiting_human","pending_approvals":[{"resource_type":"tool","resource_id":"delete_account","action":"delete_account"}]}
```

事件类型：`run.started` / `step.completed` / `run.completed` / `run.failed` / `run.awaiting_human` / `run.approved` / `run.rejected`。

> 流一定以 `run.completed`、`run.failed` 或 `run.awaiting_human` 之一收尾。事件在**落库之后**才推送，因此客户端收到的 `step.completed` 对应的步骤必然已持久化。
> `POST /v1/runs/{id}/actions` 目前只返回 JSON，不提供 SSE；`run.approved` / `run.rejected` 供后续 Console 订阅使用。

---

## 12. 错误码

| code | HTTP | 场景 |
|------|------|------|
| `INVALID_ARGUMENT` | 400 | 参数缺失/非法 |
| `UNAUTHORIZED` | 401 | 无 token / token 失效 |
| `PERMISSION_DENIED` | 403 | 功能权限或资源授权不足 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在或跨租户 |
| `INVALID_STATE` | 409 | 状态冲突（如对非 awaiting_human 的 run 提交审批）|
| `RATE_LIMITED` | 429 | 限流 |
| `TOOL_EXECUTION_FAILED` | 500 | 工具执行异常 |
| `MODEL_UNAVAILABLE` | 503 | LLM 调用失败/超时 |
| `TIMEOUT` | 504 | 运行超时 |
| `INTERNAL_ERROR` | 500 | 未归类内部错误 |

---

## 附：权限点清单

| 权限点 | 说明 |
|--------|------|
| `agent:create` / `agent:edit` / `agent:view` / `agent:delete` | Agent 管理 |
| `tool:register` / `tool:view` | 工具注册/查看 |
| `skill:register` / `skill:view` | 技能注册/查看 |
| `run:execute` / `run:view` / `run:cancel` | 运行管理（`run:view` 兼管成本查询）|
| `eval:manage` / `eval:view` | 评测集与评测任务（V1.1）|
| `experiment:manage` / `experiment:view` | A/B 实验（V1.1）|
| `role:manage` / `grant:manage` / `user:manage` | IAM 管理（admin）|
