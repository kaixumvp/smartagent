# Capability Registry — v0.3 (Tool Registry + MCP/API Runtime Tools)

企业级 Agent 能力管理平台的 **Tool Registry**。

> **当前版本 v0.3.0。** 范围：Tool CRUD + PostgreSQL(JSONB Manifest) + Web 管理页面、
> **MCP Provider 同步**、**HTTP API Tool 执行**与 Platform Runtime 标准 Tool 集成。
> 不含：Discovery / Permission（对应 v0.5）。
>
> **独立部署、HTTP 集成**：Capability 不依赖 Platform Python 包或数据库；Platform Runtime 经内部 HTTP API 消费启用的 API/MCP Tool。
> 设计与版本文档统一维护在 [`documentation/capability/`](../../documentation/capability/)，版本线见[版本路线图](../../documentation/capability/version-roadmap.md)
> 与仓库根的 [`VERSIONS.md`](../../VERSIONS.md)。
>
> ⚠️ 管理 API 无用户鉴权、CORS 为 `*`、`auto_create_tables` 默认开启。管理界面测试 API/MCP Tool 会真实调用远端，可能产生副作用。默认禁止 API Tool 访问非公网 HTTPS 地址；只有对可信目标才显式允许内网访问。Agent Runtime 集成使用独立的服务端共享密钥；不要将该密钥放进前端代码。

> **Workflow 基础能力已实现于 Capability。** 支持版本化 DAG 草稿/发布、Tool/API/条件/转换节点、运行追踪、人工输入与审批暂停/恢复；前端提供画布编辑、连线配置和待办中心。发布后的 Workflow 通过 `/internal/tools` 作为标准 Tool 投影给 Platform Runtime。管理 API 仍沿用现有无用户鉴权边界；人机交互授权需在后续治理阶段补齐。设计见[Workflow 设计](../../documentation/capability/workflow-design.md)。

配置 MCP 凭据前，需要在 Capability 项目根目录的 `.env` 中设置持久化密钥
`MCP_AUTH_ENCRYPTION_KEY`。生成方法：

```bash
cd backend
poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把命令输出写入 `application/capability/.env`：

```dotenv
MCP_AUTH_ENCRYPTION_KEY=<生成的 Fernet key>
```

此密钥用于加密数据库中的 MCP Provider 与 API Service 凭据。必须妥善备份并在重启/迁移时保持不变；丢失密钥将无法解密已保存的凭据。`.env` 不应提交到版本控制。

若要让 Platform Agent Runtime 使用这里的 API/MCP Tools，还需生成一个仅供后端互通的共享密钥，并在 Capability 与 Platform 两个后端的 `.env` 中设置相同的 `CAPABILITY_INTEGRATION_KEY`。Platform 后端另外设置 `CAPABILITY_REGISTRY_URL`（本地 Poetry 开发默认 `http://localhost:8010`；容器部署请使用后端可访问的 Registry 地址）。此密钥不传给浏览器；Tool 目录和调用都由 Platform 后端经 Capability 内部 API 代理，模型仅收到标准 Tool 名称、描述、JSON Schema 和结果。

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
  pyproject.toml  Poetry 依赖定义
  poetry.lock     锁定的后端依赖版本
  poetry.toml     项目内虚拟环境配置
  app/            main / config / database / models / schemas / manifest / mcp_client / workflow_engine
  app/routers/    tools.py · providers.py · workflows.py · internal.py
  alembic/        数据库迁移（0001–0005，含 Workflow 版本/运行/交互表）
frontend/         React 前端
  src/pages/      ToolCatalog / ToolEditor / Providers / ProviderDetail
mock-server/      真实 FastMCP server（3 个工具），用于验证同步
../../documentation/capability/  产品章程、架构、版本路线图与版本规格
```

## 快速启动（Docker Compose）

```bash
docker compose up --build
```

启动后（**宿主端口已从 3000/8000/5432 移开**，以便与业务层同时运行）：

- 前端：http://localhost:3010
- 后端 API 文档（Swagger）：http://localhost:8010/docs
- 健康检查：http://localhost:8010/health
- PostgreSQL：localhost:**5433**（业务层占用 5432）

> 端口之所以要挪：`application/platformagent/backend/docker-compose.yml` 发布 5432，
> 业务层的 uvicorn 用 8000。两栈若都用默认端口，后起的那个会启动失败或静默连错库。

## 同步一个 MCP Provider

```bash
# 起一个真实 MCP server（streamable HTTP，:9000/mcp）
cd backend
poetry run python ../mock-server/server.py

# Docker Compose 中的后端访问宿主机 MCP Server 时使用：
# http://host.docker.internal:9000/mcp
# 若后端直接运行在宿主机，再使用 http://localhost:9000/mcp。
# 在 Providers 页面 Connect 该 endpoint，
# 点 Sync 拉取 tools/list
```

## 本地开发

### 1. 启动 PostgreSQL

```bash
docker compose up -d db
```

### 2. 后端

```bash
cd backend
poetry install

# 可选：用 Alembic 建表（否则启动时 auto_create_tables 会自动建表）
poetry run alembic upgrade head

poetry run uvicorn app.main:app --reload
```

后端默认连接 `postgresql+psycopg2://registry:registry@localhost:5432/registry`，
可通过环境变量 `DATABASE_URL` 覆盖。

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

前端 http://localhost:5173 ，已配置 Vite 代理把 `/tools`、`/providers`、`/health` 转发到后端 8000。

## API

| Method | Path | 说明 |
|--------|------|------|
| POST | `/tools` | 创建 Tool |
| GET | `/tools` | 列表（`?q=` 按名称/描述模糊搜索） |
| GET | `/tools/{id}` | 详情 |
| PUT | `/tools/{id}` | 更新 |
| DELETE | `/tools/{id}` | 删除 |
| POST | `/tools/{id}/test` | 用给定 JSON 参数真实调用远端 MCP Tool；仅支持已同步且未标记 `remote_missing` 的 MCP Tool，调用超时为 30 秒 |
| POST/GET/PUT/DELETE | `/api-services` | 管理 API Base URL、认证方式、超时及私网访问策略；响应不包含凭据明文 |
| POST | `/api-tools` | 创建 HTTP API Tool：服务、method/path、标准输入输出 Schema 与请求映射 |
| PUT | `/api-tools/{id}` | 更新 API Tool 定义 |
| POST | `/api-tools/{id}/test` | 对启用的 API Tool 真实发起 HTTP 请求 |
| POST | `/providers` | 注册 MCP Provider（`name` / `endpoint` / 可选 `credential_ref`） |
| GET | `/providers` | Provider 列表（**不回显 `credential_ref`**，只给 `has_credential`） |
| GET | `/providers/{id}` | Provider 详情 |
| PUT | `/providers/{id}` | 更新 Provider endpoint 或认证设置；秘密字段永不回显 |
| POST | `/providers/{id}/sync` | 连接 MCP server 调 `tools/list`，按 `(provider_id, remote_tool_name)` upsert；远端已删的工具标记 `remote_missing` |
| DELETE | `/providers/{id}` | 删除 Provider 及其关联的 MCP 同步 Tool（本地 Tool 不受影响） |
| GET | `/internal/providers` | Platform Runtime 专用 Provider 清单（需 `X-Capability-Integration-Key`，不返回凭据） |
| GET | `/internal/providers/{id}/tools` | Platform Runtime 专用的已启用 Tool 清单（需共享密钥） |
| GET | `/internal/tools` | Platform Runtime 专用的启用 API/MCP Tool 清单，返回标准 Tool Schema（需共享密钥） |
| POST | `/internal/tools/{id}/call` | Platform Runtime 专用的 MCP/API Tool 调用代理（需共享密钥） |
| GET/POST/PUT | `/workflows`、`/workflows/{id}`、`/workflows/{id}/draft` | Workflow 列表/创建/详情/草稿保存 |
| POST | `/workflows/{id}/validate`、`publish`、`test-runs` | 校验、发布不可变版本、运行草稿 |
| GET | `/workflows/{id}/runs`、`/workflow-runs/{run_id}` | 查询运行状态及节点追踪 |
| GET/POST | `/interactions`、`/interactions/{id}/submit`、`/interactions/{id}/decide` | 待办查询、提交表单、审批决定 |
| GET | `/internal/workflows` | 已发布 Workflow manifests（需共享密钥） |
| GET | `/internal/tools` | 同时列出启用的 MCP/API Tools 与已发布 Workflow |
| POST | `/internal/tools/{id}/call` | 根据 Tool ID 调用 MCP/API Tool 或 Workflow（需共享密钥） |
| GET | `/health` | 健康检查 |

> `/sync` 是**同步请求内执行**（`asyncio.run`），失败返回 502；没有 job 表，也不记录同步历史。
> 支持无认证、Bearer Token、API Key（Header 或 Query）、自定义 Headers/Query、Basic Auth，以及 OAuth 2.0 Client Credentials。Provider 认证配置整体以 Fernet 加密后存入数据库；API 只返回认证类型和是否已配置，不回显凭据。旧的 `credential_ref` 字段仅为兼容保留，不再用于建连。

Tool Catalog 中 MCP Tool 的“测试”操作会通过 Provider 的 Streamable HTTP endpoint 调用 `tools/call`。例如请求体为 `{"arguments":{"query":"示例"}}`。本地 Tool 不能通过此接口执行；调用远端 Tool 可能产生真实副作用。

## 创建标准 API Tool

1. 在 **API Services** 中添加服务 Base URL、认证类型、请求超时；认证 JSON 在后端加密存储。
2. 默认只允许公网 HTTPS。只有确认服务目标可信时才勾选私网访问；这会允许访问内网/localhost 和 HTTP。
3. 在 Tool Catalog 新建 **API Tool**，选择 API Service，配置 method 和相对 path（例如 `/v1/weather/{city}`），并定义模型可见的 `input_schema`。
4. Query/Header/Body 模板可用 `$input.city` 引用输入；Path 中 `{city}` 会从同名输入参数取值并做 URL 编码。固定值可直接填写。
5. 将 Tool 状态设为 `active` 并启用后，在 Platform Agent 的能力选择器中添加该 API Tool。Agent Runtime 只会看到标准 Tool 名称、描述、JSON Schema 和结果；API 地址、认证凭据及请求映射保留在 Capability 后端。

### 认证配置回显

`/api-services` 的响应带 `auth_config_summary`，用于编辑时回显，**不含任何密钥明文**：

- 非敏感字段原样返回：`header_name`、`parameter_name`、`username`、`token_url`、`token_endpoint`、`token_method`、`token_content_type`、`token_body`、`token_headers`、`token_response_path`、`token_expires_in_path`、`client_id`、`scope`、`audience`、`client_auth_method`。
- 只有名字没有值：`headers` / `query_params` / `secrets` 的键，值统一为 `<redacted>`。
- `configured_secrets`：`token` / `api_key` / `password` / `client_secret` / `secrets` 中哪些已配置。
- `token_hint`：排查用形态信息——`length`、`has_bearer_prefix`、`is_jwt`、`expires_at`。
- 解密失败时只回 `{"error": "..."}`，不会让列表接口报错。

前端编辑对话框据此预填非敏感字段（**不会**把 `<redacted>` 预填进 JSON，避免误存占位符），并展示密钥是否已配置与 token 形态；表格里的认证标签可悬停查看同样信息。密钥字段留空即保留现有值。

API 执行不跟随 HTTP 重定向、不使用环境代理，并限制请求体和响应体为 1 MiB。测试/运行会真实调用目标 API，可能产生副作用。

API Tool 执行失败按来源分类返回，`detail` 始终是具体原因（`/api-tools/{id}/test` 与 `/internal/tools/{id}/call` 一致）：

| 状态码 | 来源 | 典型 detail |
|---|---|---|
| 400 | 调用方入参不满足 Tool 契约 | `Required Tool input 'city' is missing`、`Required path argument 'id' is missing or is not scalar`、超出 1 MiB 限额 |
| 422 | Tool / Service 存储定义拼不出合法请求 | `API Tool has no valid HTTP execution configuration`、`API Tool path must be a relative path...`、`API service is disabled` |
| 403 | 目标地址被网络策略拒绝 | `API service resolves to a non-public address...` |
| 502 | 远端服务或网络问题 | `API service returned HTTP 404`、`API request failed (ConnectError)`、响应超出 1 MiB |
| 504 | 请求超时 | `API request timed out` |

Service 的 Base URL / OAuth `token_url` 等存储配置不合法仍返回 503。

### Bearer Token 认证

`token` 只填 token 本身。**从接口文档复制整行 `Authorization: Bearer xxx` 进来时，`Bearer ` 前缀会在保存和注入两处自动剥离**（大小写不敏感）——所以存量数据里已经带了前缀的记录无需改数据即可恢复可用。`api_key_header` 的 `api_key` 若粘成 `X-API-Key: xxx` 同样会剥离。

token 是 JWT 时会解析 `exp`（不验签，仅用于提示）：已过期或将在 60 秒内过期的 token 直接返回 **422**，`detail` 带上具体到期时间，而不是等远端返回 401 再笼统报 502；出站日志里也会附一行 token 剩余有效期（不含 token 本身）。远端返回 401/403 时，日志会额外提示排查方向（重复前缀 / 是否过期 / scope）。

不想手工维护会过期的 token，可把 `auth_config` 从「手工 token」换成「自动获取」——只要提供 `token_endpoint` 即进入自动模式（此时 `token` 字段会被忽略）：

```json
{
  "token_endpoint": "https://sso.example.com/oauth/token",
  "token_method": "POST",
  "token_content_type": "json",
  "token_body": {"grant_type": "client_credentials", "client_id": "$secret.client_id", "client_secret": "$secret.client_secret"},
  "token_headers": {"X-Tenant": "$secret.tenant"},
  "token_response_path": "data.access_token",
  "token_expires_in_path": "data.expires_in",
  "secrets": {"client_id": "...", "client_secret": "...", "tenant": "..."}
}
```

- `token_body` / `token_headers` 里的 `$secret.<name>` 引用 `secrets` 中的值；`secrets` 与其它字段一起 Fernet 加密存储，接口不会回显。
- `token_response_path` / `token_expires_in_path` 支持点号取嵌套字段，默认 `access_token` / `expires_in`。
- 取到的 token 缓存在 **Redis**，TTL = `expires_in` 减 30 秒（未返回 `expires_in` 时默认 300 秒；剩余有效期不足 10 秒则不缓存）。缓存键是各处配置 + `secrets` 摘要的 sha256，轮换密钥会自动换键。
- `token_endpoint` 与 Base URL 受同一套网络策略约束：未开启私网访问时必须是 HTTPS。
- 想改回手工 token，把 `token_endpoint` 传空串即可清除自动获取配置。

Redis 由 `docker-compose.yml` 的 `redis` 服务提供（`redis:7-alpine`，host 端口 **6380**，避免与业务层的 6379 冲突），backend 通过 `REDIS_URL` 连接。**Redis 连不上不影响调用**：读取/写入失败只记一条 warning，然后照常去取新 token。`TOKEN_CACHE_ENABLED=false` 可整体关闭缓存。OAuth 2.0 `client_credentials` 与 bearer 自动获取共用这套缓存。

`API_TOOL_HTTP_LOG`（默认 `true`）会把 API Tool 的出站请求/响应打进服务日志（`docker logs capability-backend-1`）：method、完整 URL、header、body、query、超时设置、响应状态/耗时/响应体（非 2xx 也会打远端返回体，便于排查）。凭据按 header / query 参数名自动脱敏（`Authorization: Bearer <redacted>`、`api_key=<redacted>`），body 与响应体各截断到 2000 字符；设为 `false` 可关闭。业务 logger 由 `app/main.py` 配置，httpx 自带的请求日志被压到 WARNING，避免它把 query 里的密钥原样打出来。

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

Tool 的权威文档以 JSONB 存储，六段结构（详见[系统架构文档](../../documentation/capability/system-architecture.md) §7）：

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

> 本地 Tool 的 `source=local`、`provider: null`；经 MCP 同步进来的 Tool 会填入 `provider` 绑定信息。
> `discovery` 段目前只被**写入**（`manifest.py` 里生成），**没有任何查询路径读取它** ——
> Discovery 是 v0.5 的工作。同理 `metadata.tags` / `keywords` 存在 JSONB 里，
> 但 `/tools?q=` 目前只模糊匹配 `display_name` 与 `description`，**搜不到 tag**。
