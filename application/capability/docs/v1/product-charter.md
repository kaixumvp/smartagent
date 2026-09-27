# Capability Registry — Product Charter

> 产品章程（CA）

Version: 1.0

Owner: Heiiyo

Status: Draft

---

# 1. 产品愿景

Capability Registry 是一个企业级 Agent 能力管理平台，用于统一管理 Tool、Skill、Workflow 等能力资产，并向 Runtime、Workflow Designer、Agent 提供标准化 Discovery 能力。

v1 只聚焦 **Tool Registry**。

一句话：

> 统一注册、统一发现、统一治理企业 Tool。

---

# 2. 产品目标

建立一个企业级 Tool 管理中心，实现：

- Tool 注册
- Tool Catalog
- MCP Tool 接入
- 本地元数据管理
- Tool Discovery
- 权限元数据管理

不负责：

- Tool 执行
- Agent Runtime
- Workflow 执行

> 权限边界：仅指「权限元数据管理」——Registry 只存储/返回 `permission_group` 等元数据，**不执行鉴权**，鉴权在 Runtime 侧完成。这与「不包含 RBAC」一致。

---

# 3. 用户角色

## Platform Admin

负责：

- 管理 MCP Server
- 注册 Tool
- 编辑 Tool
- 设置权限
- 同步 Tool

## Agent Runtime

只调用 Registry：

- 查询 Tool
- Discovery Tool
- 获取 Metadata

不执行管理功能。

---

# 4. MVP 范围

## 包含

- Tool CRUD
- MCP Provider
- Tool Registration
- Discovery
- Catalog
- Permission Metadata

## 不包含

- Skill
- Workflow
- LLM
- Memory
- Multi Tenant
- RBAC

---

# 5. 产品价值

| 价值 | 说明 |
|------|------|
| 统一管理 | 所有 Tool 一个入口 |
| 可发现 | Agent 动态搜索 Tool |
| 可治理 | 标签、权限、生命周期、审计 |
| 可扩展 | 后续支持 Skill Registry |
| 解耦 | Runtime 与 Tool 分离 |

---

# 6. 成功标准

平台管理员能够：

- 5 分钟接入一个 MCP Server
- 自动同步 Tool
- 编辑本地元数据
- Discovery 搜索 Tool
- Runtime 获取 Tool Metadata

即视为 v1 成功。

量化指标（目标值待定，作为验收基准）：

- Discovery 响应 P95 < 200ms（1000 Tool 规模）
- 单 Provider 接入（含首次同步）≤ 5 分钟
- 同步成功率 ≥ 99%
- 无命中场景返回空列表而非报错