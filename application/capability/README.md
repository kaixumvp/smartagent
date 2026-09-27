# Capability Registry — v0.1 (Local Tool Registry)

企业级 Agent 能力管理平台的 **Tool Registry** 最小可用版本（MVP）。

> 范围：Tool CRUD + PostgreSQL(JSONB Manifest) + Web 管理页面。
> 不含：MCP Provider / Discovery / Permission（对应 v0.2 / v0.5）。

## 技术栈

| 层 | 技术 |
|----|------|
| Frontend | React + Ant Design + Vite |
| Backend | FastAPI + SQLAlchemy 2.0 |
| Database | PostgreSQL（JSONB） |
| Migration | Alembic |

## 目录结构

```
backend/          FastAPI 后端
  app/            main / config / database / models / schemas / manifest / routers
  alembic/        数据库迁移
frontend/         React 前端
  src/pages/      ToolCatalog / ToolEditor
docs/v1/          设计文档（产品章程、架构、版本规划、原型）
```

## 快速启动（Docker Compose）

```bash
docker compose up --build
```

启动后：

- 前端：http://localhost:3000
- 后端 API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 本地开发

### 1. 启动 PostgreSQL

```bash
docker compose up -d db
```

### 2. 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 可选：用 Alembic 建表（否则启动时 auto_create_tables 会自动建表）
alembic upgrade head

uvicorn app.main:app --reload
```

后端默认连接 `postgresql+psycopg2://registry:registry@localhost:5432/registry`，
可通过环境变量 `DATABASE_URL` 覆盖。

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

前端 http://localhost:5173 ，已配置 Vite 代理把 `/tools`、`/health` 转发到后端 8000。

## API

| Method | Path | 说明 |
|--------|------|------|
| POST | `/tools` | 创建 Tool |
| GET | `/tools` | 列表（`?q=` 按名称/描述模糊搜索） |
| GET | `/tools/{id}` | 详情 |
| PUT | `/tools/{id}` | 更新 |
| DELETE | `/tools/{id}` | 删除 |

创建/更新请求体示例：

```json
{
  "display_name": "员工信息查询",
  "description": "按姓名/工号查询员工信息",
  "lifecycle_state": "draft",
  "version": "1.0.0",
  "tags": ["hr", "employee"],
  "keywords": ["员工", "查询"],
  "input_schema": { "type": "object", "properties": {} },
  "output_schema": { "type": "object" }
}
```

## Manifest 结构

Tool 的权威文档以 JSONB 存储，六段结构（详见 `docs/v1/system-architecture.md` §7）：

```json
{
  "identity": { "name": "...", "display_name": "...", "version": "1.0.0" },
  "provider": null,
  "metadata": { "description": "...", "owner": null, "tags": [], "keywords": [] },
  "discovery": { "enabled": false, "intents": [] },
  "permission": null,
  "contract": { "input_schema": {}, "output_schema": {} }
}
```

> v0.1 为本地 Tool（`source=local`，Runtime 自行执行），尚无 Provider 绑定与 Discovery。
