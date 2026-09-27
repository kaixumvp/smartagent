
# Capability Registry — Version Roadmap

> 项目版本规划（Version Management）

**Project:** Capability Registry

**Current Target:** v1.0.0

**Architecture:** Control Plane（Tool Registry）

---

# 1. Roadmap

| Version | Milestone | Status |
|----------|-----------|--------|
| v0.1.0 | Local Tool Registry | ⏳ Planned |
| v0.2.0 | MCP Provider & Sync | ⏳ Planned |
| v0.5.0 | Discovery & Permission | ⏳ Planned |
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
v0.5
 │
 │ Discovery + Permission
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

- [ ] Tool CRUD
- [ ] PostgreSQL
- [ ] JSONB Manifest
- [ ] Swagger API

### Frontend

- [ ] Tool Catalog
- [ ] Tool Editor
- [ ] Create Tool
- [ ] Delete Tool

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

- [ ] Provider CRUD
- [ ] MCP Connection
- [ ] listTools()
- [ ] Tool Registration
- [ ] Sync Button

### New Pages

- [ ] MCP Providers
- [ ] Provider Detail

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

# 5. v0.5.0 — Discovery & Permission

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

- [ ] Tool CRUD
- [ ] Catalog
- [ ] Editor
- [ ] PostgreSQL

## v0.2

- [ ] Provider
- [ ] MCP Sync
- [ ] Registration

## v0.5

- [ ] Discovery
- [ ] Permission
- [ ] Search

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
| v2.1 | Workflow Designer |
| v2.5 | Skill Manifest |
| v3.0 | Vector / Semantic (Intent) Discovery |
| v3.5 | RBAC |
| v4.0 | Multi-Tenant |
| v5.0 | Capability Marketplace |

> v1.x 只关注 Tool Registry；v2 开始进入 Skill 与 Workflow，不破坏现有数据模型。