# SmartAgent · Business Layer

The business layer answers: **which Agent runs, as whom, with what permissions, where the result is stored, and how it is exposed over HTTP.** The agent loop itself belongs to the framework layer.

| | |
|---|---|
| Status | **0.3.0** (原 V0.2 收口 + 原 V1.1 的评测/灰度/成本). 0.4.0 / 0.5.0 not started — see the [PlatformAgent roadmap](../../../documentation/platformagent/版本规划.md) and the repo-root `VERSIONS.md` |
| Stack | Python 3.11–3.14 · FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2 · PostgreSQL + pgvector · Redis |
| Design docs | [业务层详细设计](../../../documentation/platformagent/业务层详细设计.md) · [API 文档](../../../documentation/platformagent/API文档.md) · [版本规划](../../../documentation/platformagent/版本规划.md) |

## Two layers, one repository

```
application/
├── platformagent/backend/   ← business layer  (this README)
└── ouroboros/               ← agent framework (vendored as a path dependency, 2.0.0)
```

`ouroboros` owns the Plan → Decide → Execute → Observe loop, the plugin/skill/tool protocols, and memory
mechanics. It defines **ports** (`ouroboros.ports`); the business layer implements host-side ports as
**adapters** and composes documented framework modules such as gateways, registries, and memory. It does
not depend on private `core` node/state implementations. The framework never imports the business layer.

The single entry point into the framework is `AgentRuntime.run(...)` / `.resume(...)`
(`ouroboros/src/core/runtime.py`).

> Framework API changes are the business layer's first priority — see the "contract details" in
> [业务层详细设计](../../../documentation/platformagent/业务层详细设计.md) §4 for the non-obvious ones. They are the kind of mismatch that
> compiles fine and fails silently, so read that section before touching `src/smartagent/services/run_service.py`.

## Directory structure

```
src/smartagent/
├── main.py                  # FastAPI entrypoint: routers, middleware, error format, Scalar docs, lifespan
├── config.py                # Settings (pydantic-settings) — every knob is an env var
├── pricing.py               # Token price table + estimate_cost (the source of runs.cost)
├── util.py                  # new_id ({prefix}_{uuid4hex} PK convention) + utcnow
├── api/                     # HTTP semantics only
│   ├── deps.py              #   DI: gateways (shared + judge), embedder, vector store, memory, permissions
│   ├── security.py          #   JWT issue/verify, PBKDF2, current principal, require_permission/require_admin
│   ├── middleware.py        #   trace_id propagation + Redis token-bucket rate limiting
│   ├── sse.py               #   host-side SSE serialization (the framework only emits RuntimeEvent)
│   ├── schemas.py           #   request/response models
│   └── routes/              #   15 routers — see "API overview"
├── services/                # Orchestration: neither HTTP semantics nor a framework port
│   ├── run_service.py       #   assemble AgentDefinition/RuntimeDeps → run/resume → persist + memory + audit + cost
│   ├── evaluation_service.py#   async evaluation jobs (own sessions, bounded concurrency, restart sweep)
│   └── experiment_service.py#   deterministic sticky A/B assignment
├── adapters/                # Implementations of ouroboros.ports
│   ├── run_recorder.py      #   EventSink      → run_steps + terminal state + SSE fan-out
│   ├── db_checkpointer.py   #   Checkpointer   → runs.checkpoint (survives the request, so HITL can resume)
│   ├── subagent_runner.py   #   SubagentRunner → child runs linked by parent_run_id
│   ├── pgvector_memory.py   #   LongTermMemory → pgvector write/recall
│   ├── cost_gateway.py      #   per-run gateway: tier routing + cost ledger
│   ├── llm_judge.py         #   Judge          → LLM-as-judge with a degraded fallback
│   ├── db_plugin_loader.py  #   agents.config.plugins → PluginRegistry (builtin / MCP / HTTP-OpenAPI)
│   └── audit.py             #   audit_logs writer + permission-decision buffer
├── iam/                     # RBAC + Grant data loading → ouroboros PermissionContext
└── db/                      # SQLAlchemy ORM (22 tables) + engine/session
```

Dependency direction is one-way: `api → services → adapters → ouroboros(ports)`. `db` and `iam` are used by
all three. Adapters never import `services` — the sub-agent cycle is broken by injecting a bound method
(`RunService._run_child`) into `DbSubagentRunner` at construction time.

## Quick start with Docker Compose

```bash
# Run from application/platformagent/backend
# PowerShell; copy only if you do not already have a configured .env
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
docker compose ps
```

Compose starts PostgreSQL + pgvector, Redis, the API, and the production-built React
console. It waits for the database, applies Alembic migrations, then starts the API and
console. The API is at `http://localhost:8000`, the console at `http://localhost:3000`,
and the API reference at `http://localhost:8000/docs`.

Before starting, set a strong `JWT_SECRET` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`.
Set `DEEPSEEK_API_KEY` to enable LLM calls. To use MCP tools from a separately running
Capability Registry, set the matching `CAPABILITY_INTEGRATION_KEY` in this `.env` and
in the Registry, and make its API available on the host at port 8010. The container
reaches that host service at `http://host.docker.internal:8010`.

`docker compose down` stops the services and preserves database data. Do not use
`docker compose down -v` unless you intend to delete the database volume.

## Quick start for local development

```bash
# Run from application/platformagent/backend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d postgres redis
poetry install
poetry run alembic upgrade head
poetry run uvicorn smartagent.main:app --reload
```

In another terminal, run the frontend with `npm install` and `npm run dev` from
`application/platformagent/frontend`; Vite proxies API requests to port 8000.

**Getting an account.** There is no self-registration — accounts only mean something inside a tenant, with
roles and grants attached, so they are created by someone holding `user:manage`. Bootstrap:

1. `POST /v1/auth/login` as `admin` with whatever `BOOTSTRAP_ADMIN_PASSWORD` you set (default `admin123`).
2. `POST /v1/auth/change-password` immediately if you took the default.
3. `POST /v1/users` to create everyone else, assigning roles by name.

Interactive API reference: `GET /docs` (Scalar).

**Tests need none of this** — see below.

## Configuration

Everything lives in `config.py` as a `Settings` field and is overridable by an env var of the same name
(upper-cased). `.env.example` lists them all. The ones that change behaviour most:

| Setting | Effect |
|---|---|
| `AUTH_ENABLED=false` | Bypasses JWT and returns a system **admin** principal. Note this also disables the HITL approval path, because `check_permission` allows admins outright. |
| `CAPABILITY_REGISTRY_URL` + `CAPABILITY_INTEGRATION_KEY` | Reads Capability MCP Provider/Tool metadata and invokes selected remote tools through the Capability backend. Set the same integration key in both backends; it is never sent to the browser. |
| `LLM_ROUTING_ENABLED` + `LLM_CHEAP_MODEL` / `LLM_EXPENSIVE_MODEL` | Routes agents that pinned no `config.model` by task complexity. An agent that *did* set `config.model` always keeps it. |
| `LLM_CACHE_ENABLED` | Wraps the shared gateway in a prompt cache. Process-local, so hit rates are per worker. |
| `JUDGE_MODEL` | Scoring model for evaluations. Separate from the business model on purpose: it bypasses routing and caching so scores stay comparable. Falls back to `LLM_MODEL`. |
| `EVAL_CONCURRENCY` | Evaluation cases in flight; each holds its own DB session. |
| `EVAL_SWEEP_ON_STARTUP=false` | Skips the startup sweep of interrupted evaluations. Turn off where startup must not touch the database. |
| `MODEL_PRICES` | JSON overriding `pricing.py`. A model with no price is billed as 0 and logged — an explicit gap beats a wrong number. |

## API overview

31 paths / 42 operations under `/v1` (except `/health` and `/docs`). Full reference with payloads:
[API 文档](../../../documentation/platformagent/API文档.md).

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/login` (optional `tenant`; ambiguous usernames are rejected, not silently resolved), `POST /auth/change-password` |
| Users | `POST/GET /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/password` — `user:manage`, scoped to the caller's tenant. **No self-registration** (see below) |
| Agents | `POST/GET /agents`, `GET/PATCH/DELETE /agents/{id}` — re-posting a name publishes a version; delete is a soft delete that keeps history |
| Runs | `POST/GET /agents/{id}/runs` (`stream: true` → SSE), `GET/DELETE /runs/{id}`, `POST /runs/{id}/actions` (HITL approve/reject) |
| Tools / Skills | `POST/GET /tools`, `POST/GET /skills`, `GET /skills/{id}` |
| IAM | `POST/GET /roles`, `POST /roles/{id}/permissions`, `POST/GET/DELETE /grants` |
| Memory | `POST /memory/recall` |
| Evaluation | `POST/GET /golden-sets`, `POST/GET /evaluations` (async, 202 + poll), `POST/GET /runs/{id}/feedback` |
| Experiments | `POST/GET /experiments`, `POST /experiments/{id}/status`, `GET /experiments/{id}/results` |
| Cost | `GET /cost/summary`, `GET /cost/cache` |

SSE events: `run.started` → `step.completed`* → one of `run.completed` / `run.failed` / `run.awaiting_human`.
Events are pushed **after** they are persisted, so a step the client sees is already durable.

## Database

22 tables across five Alembic revisions. `alembic upgrade head` applies them in order.

| Revision | Contents |
|---|---|
| `0001` | tools / agents / agent_tools / runs / run_steps + builtin tool seed |
| `0002` | multi-tenancy, IAM (6 tables), grants, skills, vector_memories, audit_logs + role/permission/admin seed |
| `0003` | `runs.checkpoint` + `runs.pending_approvals` (mid-run HITL) |
| `0004` | evaluation (5 tables), experiments (2 tables), `agents.is_latest`, run attribution columns, 4 permission codes |
| `0005` | optional `runs.conversation_id` for persistent Agent chat sessions |

Primary keys are minted by the application as `{prefix}_{uuid4hex}` (`util.new_id`) — `agent_`, `run_`,
`step_`, `mem_`, `eval_`, `exp_`, …

## Tests

```bash
poetry run pytest -q          # 79 tests, ~6s, no PostgreSQL/Redis/LLM required
```

`conftest.py` disables rate limiting and the startup sweep, and provides a `FakeSession` that understands
`select(...).where(...).order_by(...)`. A real database is not an option in tests: the models use `JSONB`
and pgvector `Vector`, which SQLite cannot compile.

| File | Covers |
|---|---|
| `test_api.py` (9) | 0.2.0 acceptance matrix: {high-risk tool present, absent} × {sync, SSE}, plus approve → resume continues the *same* run |
| `test_runtime.py` (7) | Business-side assembly (`AgentDefinition`/`RuntimeConfig` derivation) and `RunRecorder` persistence |
| `test_iam.py` (8) | RBAC, grants, permission decisions |
| `test_plugins.py` (7) | Plugin assembly from the tools/skills tables |
| `test_subagent.py` (3) | Agent-skill dispatch and recursion guards |
| `test_evaluation.py` (10) | Judge parsing/degradation, async job end-to-end, restart sweep |
| `test_experiments.py` (11) | Bucketing determinism and weights, assignment stickiness, agent versioning |
| `test_cost.py` (12) | Pricing, model pinning vs tier routing, cost attribution through a real run |
| `test_users.py` (12) | Account creation and role binding, password rotation, self-lockout guard, delegation via `user:manage` |

The agent loop itself is covered by the framework's own suite (`ouroboros/tests/`) — the business tests
deliberately do not re-test it.

## Notes

- **`runs` / `run_steps` are the source of truth.** The Redis Working Brain is a volatile cache; anything
  that must be auditable goes to PostgreSQL.
- **Multi-tenancy is a hard line.** Every query filters on `tenant_id`; a cross-tenant resource returns 404,
  never 403 (which would leak its existence).
- **`runs.cost` is only meaningful from 0.3.0 onward** (原 V1.1). The column existed since `0001` but
  nothing wrote it, so older runs report 0. `RunOut` now returns both `cost` and `model`.
- **Evaluation jobs run in-process** and are lost on restart; the startup sweep marks the strays `failed`.
  Out-of-process scheduling is 0.5.0 work.
- **`langgraph` has been dropped** from both `pyproject.toml` files. It was declared but never imported —
  the framework replaced the graph loop with its own `AgentRuntime`.
