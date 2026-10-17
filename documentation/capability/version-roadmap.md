
# Capability Registry — Version Roadmap

> 本文档统一归档于仓库根的 `documentation/capability/`。

> 项目版本规划（Version Management）

**Project:** Capability Registry

**Current Version:** v0.3.0

**Next Target:** v0.5.0 (Discovery & Permission)

**Architecture:** Control Plane（Tool Registry）

---

# 1. Roadmap

| Version | Milestone | Status |
|----------|-----------|--------|
| v0.1.0 | Local Tool Registry | ✅ Delivered |
| v0.2.0 | MCP Provider & Sync | ✅ Delivered |
| v0.3.0 | API Tools & Runtime Integration | ✅ Delivered (current) |
| v0.5.0 | Discovery & Permission | ⏳ Planned |
| v0.6.0 | Visual Workflow Builder & Deterministic Execution | ⏳ Proposed |
| v1.0.0 | Enterprise Tool Registry | 🎯 Target |

---

# 2. Version Timeline

```text
v0.1
 │
 │ Local Tool CRUD
 ▼
v0.2
 │
 │ MCP Provider
 ▼
v0.3
 │
 │ HTTP API Tools + Runtime bridge
 ▼
v0.5
 │
 │ Discovery + Permission
 ▼
v0.6
 │
 │ Visual Workflows
 ▼
v1.0
 │
 │ Enterprise Tool Registry
 ▼
Future
```

---

# 3. v0.1.0 — Local Tool Registry

## Goal

完成最小可运行的 Tool 管理中心。

### Backend

- [x] Tool CRUD
- [x] PostgreSQL
- [x] JSONB Manifest
- [x] Swagger API

### Frontend

- [x] Tool Catalog
- [x] Tool Editor
- [x] Create Tool
- [x] Delete Tool

### Deliverable

```text
Tool Catalog
Tool Detail
Tool Edit
Docker Compose
```

### Git Tag

```bash
git tag v0.1.0
```

---

# 4. v0.2.0 — MCP Provider & Sync

## Goal

接入外部 MCP Server，实现 Tool Registration。

### New Features

- [x] Provider CRUD
- [x] MCP Connection
- [x] listTools()
- [x] Tool Registration
- [x] Sync Button

### New Pages

- [x] MCP Providers
- [x] Provider Detail

### Deliverable

```text
MCP Connect
Tool Sync
Registration
```

### Git Tag

```bash
git tag v0.2.0
```

---

# 5. v0.3.0 — API Tools & Runtime Integration

## Goal

把普通 HTTP API 映射为标准 Runtime Tool，同时让 Agent 不接触原始 HTTP 配置或认证凭据。

### New Features

- [x] API Service CRUD with encrypted credentials
- [x] API Tool method/path and argument mapping
- [x] SSRF protections, redirect blocking, request/response size limits
- [x] Shared-key-protected internal Tool catalog and call bridge
- [x] Platform Agent Tool binding and runtime invocation

---

# 6. v0.5.0 — Discovery & Permission

## Goal

实现企业级 Tool Discovery。

### New Features

- [ ] Discovery API
- [ ] Keyword Search
- [ ] Tag Search
- [ ] Description Search
- [ ] Permission Group
- [ ] Enable / Disable

### UI

- [ ] Search Bar
- [ ] Provider Filter
- [ ] Status Filter
- [ ] Permission Filter

### Deliverable

```text
POST /discover
Catalog Search
Permission Metadata
```

### Git Tag

```bash
git tag v0.5.0
```

---

# 6. v1.0.0 — Enterprise Tool Registry

## Goal

形成完整的企业级 Tool Registry。

### Dashboard

- [ ] Tool Statistics
- [ ] Provider Statistics
- [ ] Active Tools
- [ ] Offline Providers

### Registry

- [ ] Tool Lifecycle
- [ ] Provider Status
- [ ] Sync History
- [ ] Catalog Management

### Frontend

- [ ] Dashboard
- [ ] Tool Catalog
- [ ] Tool Editor
- [ ] Provider Management

### Deliverable

```text
Enterprise Web Console
Tool Registry
MCP Registration
Discovery
Permission
```

### Git Tag

```bash
git tag v1.0.0
```

---

# 7. Milestone Checklist

## v0.1

- [x] Tool CRUD
- [x] Catalog
- [x] Editor
- [x] PostgreSQL

## v0.2

- [x] Provider
- [x] MCP Sync
- [x] Registration

## v0.5

- [ ] Discovery
- [ ] Permission
- [ ] Search

## v0.6

- [ ] Versioned Workflow definitions and publication validation
- [ ] Visual DAG editor with Tool/API nodes and condition branches
- [ ] Declarative pre/post logic and bounded execution trace
- [ ] Expose published Workflow as a standard PlatformAgent Tool
- [ ] Durable execution jobs with pause/resume for structured human input and approval
- [ ] Interaction Inbox with submit/approve/reject/return and explicit timeout paths

详细范围与边界见[Workflow 设计](./workflow-design.md)。v0.6.0 是建议的路线图拆分，实施前应按 v0.5 权限基线评估调整。

## v1.0

- [ ] Dashboard
- [ ] Lifecycle
- [ ] Enterprise Console

---

# 8. Git Branch Strategy

```text
main

develop

feature/tool-crud

feature/provider

feature/mcp-sync

feature/discovery

feature/dashboard
```

开发流程：

```text
feature/*
      │
      ▼
develop
      │
      ▼
release/v1.0
      │
      ▼
main
```

---

# 9. Release Notes Template

## v0.1.0

**Added**

- Tool CRUD
- Tool Catalog
- Manifest

**Changed**

- Initial database schema

---

## v0.2.0

**Added**

- MCP Provider
- Tool Registration
- Sync Service

---

## v0.5.0

**Added**

- Discovery API
- Permission Group
- Tool Search

---

## v1.0.0

**Added**

- Dashboard
- Provider Status
- Lifecycle
- Enterprise Tool Registry

---

# 10. Future Versions

| Version | Feature |
|----------|---------|
| v2.0 | Skill Registry |
| v2.1 | （原始长期设想；Workflow 已建议提前至 v0.6.0） |
| v2.5 | Skill Manifest |
| v3.0 | Vector / Semantic (Intent) Discovery |
| v3.5 | RBAC |
| v4.0 | Multi-Tenant |
| v5.0 | Capability Marketplace |

> 此表是初始产品愿景中的远期占位，并非已承诺版本计划；近期 Workflow 范围以 v0.6.0 提案和[Workflow 设计](./workflow-design.md)为准。