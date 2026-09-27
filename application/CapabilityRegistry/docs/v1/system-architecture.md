# Capability Registry — System Architecture

> 整体架构设计

Version: 1.1

---

# 1. 系统定位

Capability Registry 是 Agent 平台的 **Control Plane**。

职责：

- Tool Registry
- Discovery
- Metadata
- Provider
- Permission Metadata

不负责 Runtime。

---

# 2. 总体架构

```text
                    Web Admin Console
                            │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
 Tool Catalog            Tool Editor          MCP Provider
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                          REST API
                               │
                Capability Registry Service
                ┌────────────┬────────────┬───────────────┐
                │            │            │               │
           Tool Service  Provider Service  Discovery   Sync Service
                │            │            │               │
                └────────────┴─────┬──────┴───────────────┘
                                   │
                              PostgreSQL
```

> 同步控制流（数据如何进入 Registry，与存储流分离）：

```text
Admin 点击 Sync
      │
      ▼
Sync Service ──► MCP Adapter ──► External MCP Server (listTools / schema)
      │                              │
      └──────────── 写回 ────────────┘
                   │
               PostgreSQL
```

> 运行时调用流（Registry 不执行 Tool，只返回 Metadata）：

```text
Agent ─► Runtime ─► Registry (获取 Metadata) ─► MCP Client ─► Original MCP Server
```

---

# 3. 核心模块

## Web Console

负责管理页面：

- Dashboard
- Tool Catalog
- Tool Editor
- Provider

---

## Registry Service

负责：

- Tool CRUD
- Provider CRUD
- Metadata
- Manifest
- Discovery

---

## Sync Service

负责：

- 触发/调度同步任务（异步 job）
- 记录同步历史
- 派生 Provider status（online/offline）

---

## MCP Adapter

职责：

- 建立连接
- listTools()
- 获取 Schema
- 转换 Manifest
- Upsert Registration

不负责执行 Tool。

---

## PostgreSQL

保存：

- Provider
- Tool Registration
- Manifest（JSONB）
- 反规范化检索列（tags / keywords / permission_group）
- 同步历史

---

# 4. 数据流

## Tool 注册

```text
Admin
  │
Create Tool
  │
  ▼
Registry
  │
  ▼
PostgreSQL
```

---

## MCP 同步

```text
Admin
 │
Sync
 │
 ▼
Sync Service
 │
 ▼
MCP Adapter
 │
listTools()
 │
 ▼
Schema
 │
 ▼
Mapper
 │
 ▼
Upsert Registration
 │
 ▼
Database
```

> 同步以异步 job 执行，结果记录到同步历史。

---

## Discovery

```text
Agent Runtime
      │
POST /discover
      │
      ▼
Registry
      │
      ▼
PostgreSQL
      │
      ▼
Top K Tool
```

---

# 5. Runtime 边界

Registry 不执行 Tool。

正确流程：

```text
Agent
 │
 ▼
Runtime
 │
 ├────────► Registry
 │          获取 Metadata
 │
 ▼
MCP Client
 │
 ▼
Original MCP Server
```

Registry 仅返回：

- Provider
- Tool Name
- Permission
- Manifest

> Tool 有两类执行来源，Registry 均不执行、只返回元数据：
>
> - `local`（本地/自带 Tool）：Runtime 自身实现并直接执行，无需 Provider 绑定。
> - `mcp`（外部 Tool）：Runtime 依据返回的 Provider 信息，经 MCP Client 调用原 MCP Server。

---

# 6. 数据模型

## Provider

```text
Provider
├── id               (UUID 主键)
├── name
├── endpoint
├── credential_ref   (密钥引用，不落明文)
├── status           (online / offline，由心跳/同步派生)
└── last_sync_at
```

## Tool Registration

```text
Tool Registration
├── id                  (UUID 主键，对应 API /tools/{id})
├── source              (local / mcp，执行来源判别)
├── provider_id         (仅 source=mcp 有效)
├── remote_tool_name    (MCP 原始名称)
├── display_name
├── description
├── tags
├── keywords
├── permission_group
├── lifecycle_state     (draft / active / remote_missing)
├── enabled             (boolean，启停开关)
├── last_synced_at
└── manifest            (JSONB，权威文档)
```

> `tags` / `keywords` / `permission_group` 为反规范化列，用于 SQL 过滤与索引；由服务在写入 manifest 时同步维护，`manifest` 为唯一权威来源。
>
> v1 使用 `id` 作为 Tool 主键；统一的 `capability_id` + 类型判别（Tool / Skill / Workflow）留到 v2 引入 Capability 模型时再设计。
>
> `source` 区分执行来源（非 Capability 类型）：`local` = 项目/Agent 平台自带的 Tool，由 Runtime 自行执行；`mcp` = 外部 MCP Provider 同步的 Tool，由 Runtime 经 MCP Client 调用原 Server。

---

# 7. Manifest

Manifest 是 Tool 的权威文档（JSONB），包含 6 个段：

```text
Manifest
├── identity      身份标识
├── provider      归属
├── metadata      基础元数据
├── discovery     发现配置
├── permission    权限元数据
└── contract      输入/输出契约
```

字段级定义与示例：

```json
{
  "identity": {
    "name": "employee_lookup",
    "display_name": "员工信息查询",
    "version": "1.0.0"
  },
  "provider": {
    "provider_id": "0192f...",
    "provider_name": "hr-mcp",
    "remote_tool_name": "employee_lookup"
  },
  "metadata": {
    "description": "按姓名/工号查询员工信息",
    "owner": "hr-team",
    "tags": ["hr", "employee"],
    "keywords": ["员工", "查询", "工号"],
    "annotations": {
      "readOnlyHint": true,
      "destructiveHint": false,
      "idempotentHint": true,
      "openWorldHint": false
    }
  },
  "discovery": {
    "enabled": true,
    "intents": []
  },
  "permission": {
    "permission_group": "HR_READ",
    "scopes": ["employee:read"]
  },
  "contract": {
    "input_schema": {
      "type": "object",
      "properties": { "employee_id": { "type": "string" } }
    },
    "output_schema": { "type": "object" }
  }
}
```

| 段 | 字段 | 说明 |
|----|------|------|
| identity | name | 远端 MCP Tool 原始名称 |
| identity | display_name | 本地展示名（MCP 同步取 `Tool.title`，缺省回退 `name`） |
| identity | version | 本地元数据版本（非远端 schema 版本） |
| provider | provider_id / provider_name / remote_tool_name | 归属与远端标识 |
| metadata | description / owner / tags / keywords / annotations | 基础元数据与检索词；`annotations` 保留 MCP 行为提示（`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`） |
| discovery | enabled | 是否参与 Discovery |
| discovery | intents | v3 语义/向量检索预留，v1 留空 |
| permission | permission_group / scopes | 权限元数据（仅存元数据，不执行鉴权） |
| contract | input_schema / output_schema | 输入/输出 JSON Schema |

> v1 不引入「Intent / 语义检索」：Discovery 仅做关键词/标签匹配（见 §9）。`intents` 为 v3 预留。

---

# 8. 生命周期

`lifecycle_state` 与 `enabled` 是两个正交概念：

- `lifecycle_state`：`draft` → `active` → `remote_missing`
- `enabled`：启停开关（`active` 时才有意义）

```text
draft ──(发布)──► active ◄──(启停)──► enabled / disabled
                     │
                (远端删除)
                     │
                     ▼
               remote_missing
```

- `draft`：本地新建，未发布，不可被发现。
- `active`：已发布，`enabled=true` 时可被发现。
- `enabled=false`：管理员停用，不可被发现，保留记录。
- `remote_missing`：远端 MCP Tool 被删除（仅 `source=mcp`），标记待人工处理，不立即删除数据库记录。

---

# 9. Discovery 实现（v1）

v1 仅做确定性检索，不依赖 LLM / 向量：

| 匹配维度 | 方式 |
|---------|------|
| Name | 精确 / 模糊 |
| Description | 全文 / 模糊 |
| Keywords | 匹配 |
| Tags | 匹配 |

流程：

```text
POST /discover { query, top_k }
        │
        ▼
 多维度打分（name > description > keywords > tags，加权求和）
        │
        ▼
 过滤 enabled=true 且 lifecycle_state=active
        │
        ▼
 排序取 Top K
```

- 打分采用加权求和，各维度权重在实现时固定。
- 无命中返回空列表；命中但低于阈值时可返回空或降级结果。
- Intent / 语义检索（向量）推迟到 v3.0「Vector Discovery」。

---

# 10. 安全与鉴权

Registry 不实现 RBAC，但企业级最低要求：

- **Admin Console**：登录 + 会话（JWT / OIDC SSO）。
- **Agent Runtime**：机器身份（API Key / Service Token），仅 read 范围（Discovery / Metadata）。
- **Provider 凭据**：MCP Server 的 API Key 等密钥以 `credential_ref` 引用外部 Secret（环境变量 / Secret Manager），不落明文，`GET /providers` 不回显。

---

# 11. 技术架构

| 层级 | 技术 |
|------|------|
| Frontend | React + Ant Design |
| Backend | FastAPI |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| Migration | Alembic |
| Manifest | JSONB |
| MCP | MCP SDK |

---

# 12. 后续扩展

```text
Capability Registry
        │
        ├──────── v1
        │          Tool
        │
        ├──────── v2
        │          Skill
        │
        ├──────── v2.5
        │          Workflow
        │
        └──────── v3
                   Vector Discovery
```

保持 Tool 数据模型不变，Skill 作为新的 Capability 类型扩展。
