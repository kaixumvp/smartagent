# Knowledge Hub — v0.2 (Document KB + Hybrid Retrieval)

企业统一知识中心的**文档知识库与混合检索**服务。独立部署、HTTP 集成——与 Capability Registry 同级，
通过受保护的内部 HTTP API 接入 Agent Runtime；不做进 `platformagent`。

> **当前版本 v0.2.0。** 范围：Upload → Parser/OCR → Markdown → Chunk → Embedding → Vector 检索
> （v0.1），加 BM25 + Metadata Filter + Reranker 的混合检索与 Query Analyzer / Context Builder（v0.2）。
> 不含：多知识源 Connector、Neo4j / Knowledge Graph、Agentic Retrieval、MCP、租户/用户权限（v0.7 最后设计）。
> 设计与版本文档统一维护在 [`documentation/knowledge/`](../../documentation/knowledge/)，
> 路线图见 [`version-roadmap.md`](../../documentation/knowledge/version-roadmap.md)，
> 版本线见仓库根 [`VERSIONS.md`](../../VERSIONS.md)。
>
> ⚠️ 管理 API 无用户鉴权、CORS 为 `*`、`auto_create_tables` 默认开启；内部 Retrieve API 用可选共享密钥
> `INTEGRATION_KEY` 保护。默认 `EMBEDDER=hash` 是依赖无关的确定性伪向量，仅用于冒烟/测试——生产检索请接
> 真实 Embedding 与 Reranker。

## 技术栈

| 层 | 技术 |
|----|------|
| Frontend | React + Ant Design + Vite（极简管理台） |
| Backend | FastAPI + SQLAlchemy 2.0 |
| Database | PostgreSQL（本地开发默认 SQLite） |
| Object Storage | MinIO（本地开发默认文件目录） |
| Vector DB | Qdrant（本地开发默认内存索引） |
| Embedding | 可插拔：`hash`（无依赖）/ `http`（OpenAI 兼容） |
| OCR | 可插拔：`none` / `tesseract` |
| Reranker | 可插拔：`lexical`（无依赖）/ `http`（cross-encoder） |

## 目录结构

```
backend/            FastAPI 后端
  pyproject.toml    Poetry 依赖
  app/              main / config / database / models / schemas
  app/routers/      bases(KB·Folder) · documents · search · jobs
  app/*.py          parse · chunking · embedding · index · retrieval · ingest · storage
  tests/            pytest（SQLite 文件 + 内存索引，无需外部服务）
frontend/           React 极简管理台（知识库/上传/检索）
docker-compose.yml  PostgreSQL + MinIO + Qdrant + backend + frontend
```

## 快速启动（Docker Compose）

```bash
docker compose up --build
```

启动后（宿主端口避开业务层 5432/8000/3000 与 Capability 5433/8010/3010）：

- 前端：http://localhost:3020
- 后端 API 文档（Scalar）：http://localhost:8020/docs
- 健康检查：http://localhost:8020/health
- PostgreSQL：localhost:**5434**、Qdrant：localhost:**6333**、MinIO API：localhost:**9010**（控制台 **9011**）

> 全栈用真实 Qdrant + MinIO + PostgreSQL。默认 `EMBEDDER=hash` 让整条链路无需外部 SaaS 即可 Demo。
> 接真实语义检索时，把 [`application/knowledge/.env.example`](./.env.example) 复制为 `.env`，设
> `EMBEDDER=http`、`EMBEDDING_URL`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY`；向量维度由后端启动时
> **自动探测**，无需手填 `EMBEDDING_DIM`。可选 `RERANKER_BACKEND=http` 接 cross-encoder。
>
> ⚠️ 切换 embedding 模型会改变向量维度/空间：旧的 Qdrant collection 维度不匹配，需删除旧 collection
> 或改 `QDRANT_COLLECTION` 名重建，并重新导入文档（re-ingest）。

## CI/CD 部署

仓库的 GitHub Actions [Deploy SmartAgent](../../.github/workflows/deploy.yml) 工作流已包含 Knowledge：推送 Knowledge 目录变更时会构建并推送
backend/frontend 镜像，随后上传 Compose 配置并更新远程服务。也可在 Actions 中手动选择 `knowledge`，
或选择 `all` 一并部署。部署复用工作流已有的 ACR、SSH 配置；服务器端配置文件位于
`/opt/knowledge/.env`（可选，按需配置真实 embedding 和 `KNOWLEDGE_INTEGRATION_KEY`），持久化数据保存在
Compose volumes 中。

## 本地开发

```bash
# 后端
cd backend
poetry install                 # 安装 ouroboros 之外的依赖
poetry run uvicorn app.main:app --reload   # 默认 SQLite + 内存索引 + 本地目录，零外部依赖
poetry run pytest -q           # 全部测试，无需 PostgreSQL/MinIO/Qdrant/LLM

# 前端（可选，另开终端）
cd frontend
npm install
npm run dev                    # http://localhost:5173，代理 /v1 → 8020
```

OCR 需要 `poetry install --with ocr` 并安装系统 `tesseract`，再设 `OCR_BACKEND=tesseract`。

接真实 embedding（本地开发）：在 `backend/.env` 设 `EMBEDDER=http` + `EMBEDDING_URL/MODEL/API_KEY`
（维度自动探测），并设 `QDRANT_URL=http://localhost:6333`（先 `docker compose up -d qdrant`）。

## API

| Method | Path | 说明 |
|--------|------|------|
| POST/GET | `/v1/knowledge-bases` | 创建 / 列出知识库 |
| GET/DELETE | `/v1/knowledge-bases/{id}` | 详情 / 删除（级联文档与索引） |
| POST/GET | `/v1/knowledge-bases/{id}/folders` | 创建 / 列出文件夹 |
| POST | `/v1/knowledge-bases/{id}/documents` | 上传文档（multipart `file` + 可选 `folder_id`），入队解析作业 |
| GET | `/v1/knowledge-bases/{id}/documents` | 列出文档（可选 `folder_id`） |
| GET | `/v1/documents/{id}` | 文档详情（含 `status` / `parser_name` / `ocr_used` / 出错信息） |
| GET | `/v1/documents/{id}/download` · `/markdown` | 下载原文 / 解析后的 Markdown |
| POST | `/v1/documents/{id}/reingest` | 重建索引（作业状态机） |
| DELETE | `/v1/documents/{id}` | 删除文档及其 chunk / 索引 / 对象 |
| GET | `/v1/documents/{id}/jobs` | 该文档的作业历史 |
| GET | `/v1/jobs/{id}` | 作业详情 |
| POST | `/v1/jobs/process` | 手动跑一轮作业（Demo / 测试；生产由后台 worker 自动跑） |
| POST | `/v1/search` | Retrieve API（见下） |
| POST | `/internal/search` | 平台 adapter 用，需 `X-Integration-Key`（未配置密钥时开放） |
| GET | `/health` | 健康检查 |

### Retrieve API

`POST /v1/search`：

```json
{
  "query": "Q3 营收",
  "kb_ids": ["kb_..."],
  "top_k": 8,
  "folder_id": null,
  "mime_types": [],
  "created_after": null,
  "created_before": null,
  "rerank": true,
  "mode": "hybrid"
}
```

- `mode`：`hybrid`（默认，向量+BM25 融合）| `vector`（纯向量）| `keyword`（纯 BM25）——供 v0.2 验收对比。
- 响应 `chunks[].evidence` 携带 `document_id` / `filename` / `start_offset` / `end_offset` / `heading_path`，
  每条命中可追溯到文件与 chunk 偏移；另有 `context`（Context Builder 拼好的引用块）与
  `dense_score` / `sparse_score` / `fused_score` / `rerank_score` 四档得分。

## 说明与边界

- **文档是事实源**：Graph / Rerank 等都是派生索引；chunk 从 v0.1 起就带 `document_id` 与偏移。
- **租户/用户权限最后设计**：v0.1–v0.2 不建 Tenant/User/RBAC；检索只按资源属性（kb / folder / mime / 时间）过滤。
- **与 Platform 0.4.0 的关系**：平台若做薄文本知识闭环，必须标明可被本 Hub 替换，避免两套完整知识库分叉。
  Hub 通过 `/internal/search`（共享密钥）供平台 adapter 消费，与 Capability 的集成方式对称。
- 迁移暂用 `auto_create_tables`（与 Capability MVP 一致）；正式发版前补 Alembic 迁移。
