# Capability Registry — System Architecture

> 本文档统一归档于仓库根的 `documentation/capability/`。

> ⚠️ **本文档描述的目标架构，部分尚未实现。** 已在正文内就地标注。当前实际实现以代码与[项目 README](../../application/capability/README.md)为准。


> 整体架构设计

Version: 1.1

---

# 1. 系统定位

Capability Registry 是 Agent 平台的 **Tool Control Plane** 与服务端 Tool adapter。它是独立部署的
FastAPI + React 服务，自己的 PostgreSQL 保存 Provider、API Service 和 Tool manifest。

职责：

- Tool Registry
- MCP Provider CRUD 与 `tools/list` 同步
- API Service / API Tool 管理
- Tool 的 MCP/API 调用代理
- Metadata
- Platform Runtime 内部 HTTP 集成

当前尚未实现 Discovery/权限组授权；Registry 不负责 Agent 的规划、工作流和运行循环，Agent Runtime 位于
PlatformAgent / Ouroboros。

---

# 2. 总体架构

```text
                    Web Admin Console
                            │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
 Tool Catalog            Tool Editor       MCP Provider / API Service
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                          REST API
                               │
                Capability Registry Service
                ┌────────────┬────────────┬───────────────┐
                │            │            │               │
       Tool Service  Provider/API Service  Discovery   Sync Service
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

> 当前 Platform Runtime 调用流中，平台先从 Registry 读取启用的 Tool 描述，再在执行阶段通过后端 adapter
> 调用 Registry 的内部 API；Registry 负责将 API/MCP 请求转发到配置的目标服务。共享集成密钥只在两个后端之间使用：

```text
Platform Console ─► Platform API / Runtime
                         │
                         ├──读取 Tool Catalog──► Capability Registry
                         │                            │
                         └──调用 Tool───────────────►│
                                                      ├── API Service
                                                      └── External MCP Server
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
- API Service / API Tool CRUD
- Metadata
- Manifest
- Discovery（规划中）
- 服务端 API/MCP Tool 调用代理

---

## Sync Service

负责：

- 触发/调度同步任务（异步 job）——**当前为请求内同步执行**
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

负责在 Registry 服务端代理 API/MCP Tool 调用；不会运行 Agent 或决定是否允许某用户调用该 Tool。

管理界面可进行手动测试；Platform Runtime 也可通过受共享密钥保护的内部 API 触发已配置的 API/MCP Tool 调用。

---

## PostgreSQL

保存：

- Provider
- Tool Registration
- Manifest（JSONB）
- （v0.5 计划）反规范化检索列（tags / keywords / permission_group）——**当前未实现**
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

> **与实现不一致**：同步当前是**请求内同步执行**（`asyncio.run`），没有 job 表，也不记录同步历史。
> 异步 job + 同步历史属 v1.0 目标，尚未实现。

---

## Discovery（规划中，当前未实现）

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

Registry 不包含 Agent Runtime 的循环、规划或授权逻辑；Agent Runtime 由 PlatformAgent 中的 Ouroboros 提供。
Registry 负责保存 manifest，并按平台后端调用请求代理 API/MCP Tool 执行。

正确流程：

```text
Agent
 │
 ▼
Platform Runtime
 │
 ├──获取 Tool 描述──► Capability Registry
 │
 └──执行时经 HTTP──► Platform adapter ─► Capability Registry
                                              ├─► API Service
                                              └─► MCP Server
```

Registry catalog 公开的数据包含：

- Provider
- Tool Name
- Permission
- Manifest

> Tool 有两类服务端执行来源：
>
> - `api`：Capability 根据已保存的 API Service 凭据与映射配置发起 HTTP 请求。
> - `mcp`：Capability 根据 Provider 配置调用 MCP Server。
>
> `local`/builtin Tools 由 Platform Runtime 自身执行，不经 Capability Registry。

---

# 6. 数据模型

## Provider

```text
Provider
├── id               (UUID 主键)
├── name
├── endpoint
├── credential_ref   (密钥引用，不落明文；接口不回显，只给 has_credential)
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

> ⚠️ **当前未实现**：`tools` 表**没有** `tags` / `keywords` / `permission_group` 列。
> 这三个字段只存在于 `manifest` JSONB 内部，`/tools?q=` 也只模糊匹配 `display_name` 与 `description`，
> **搜不到 tag**。反规范化列属 v0.5 的 Discovery 工作。
>
> v1 使用 `id` 作为 Tool 主键；统一的 `capability_id` + 类型判别（Tool / Skill / Workflow）留到 v2 引入 Capability 模型时再设计。
>
> `source` 区分执行来源（非 Capability 类型）：`local` = 本地 Tool；`mcp` = MCP Provider 同步的 Tool；`api` = 指向 API Service 的 HTTP Tool。Runtime 只消费 manifest 中的标准 name/description/input schema，经 Platform adapter 和 Capability 内部 HTTP API 调用外部 MCP/API；认证与 HTTP 请求配置不会交给模型。

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

# 9. Discovery 规划（当前未实现）

规划中的 v1 Discovery 做确定性检索，不依赖 LLM / 向量。当前 API 主要提供 Tool 列表/详情、Provider 同步
与服务端调用，尚无 `/discover` endpoint，也没有对 keywords/tags 的专门搜索实现。

目标检索维度：

| 匹配维度 | 方式 |
|---------|------|
| Name | 精确 / 模糊 |
| Description | 全文 / 模糊 |
| Keywords | 匹配 |
| Tags | 匹配 |

目标流程：

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

Registry 当前没有用户登录或 RBAC；管理 API 无用户鉴权，CORS 默认为 `*`。Platform Runtime 集成 API 由
后端共享密钥保护。以下为后续生产化目标，并非当前已交付功能：

- **Admin Console**：登录 + 会话（JWT / OIDC SSO）。
- **Agent Runtime**：机器身份（API Key / Service Token），仅 read 范围（Discovery / Metadata）。
- **Provider/API Service 凭据**：当前支持认证信息加密保存；项目要求配置持久化的 Fernet 加密密钥，
  API 只返回是否配置凭据，不回显秘密。部署和密钥轮换说明见
  [Capability README](../../application/capability/README.md)。不得把共享集成密钥放入前端。

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
