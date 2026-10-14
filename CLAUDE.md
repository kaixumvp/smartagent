# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

The git root holds two top-level directories:

- `application/` — all runnable code (three independent Python/JS projects).
- `documentation/` — centralized project documentation. Cross-project documents stay at the root; project-specific design, API, usage, and roadmap documents live under `documentation/<project>/` (`platformagent/`, `ouroboros/`, `capability/`).

| Path | What it is |
|---|---|
| `application/platformagent/backend/` | **Business layer** — FastAPI service (Python 3.11–3.14, SQLAlchemy 2.0 async, Pydantic v2, PostgreSQL+pgvector, Redis); code under `src/smartagent/`. Poetry project named `smartagent`, version 0.3.0. |
| `application/platformagent/frontend/` | React/Vite console (`smartagent-console`). |
| `application/ouroboros/` | **Framework layer** — business-agnostic agent runtime, vendored as a path dependency. |
| `application/capability/` | Separate service (FastAPI + Ant Design React) registering Tool manifests (JSONB) and syncing them from external MCP servers; own `docker-compose.yml` + `mock-server/`. |

`application/platformagent/backend/README.md` is the authoritative guide to the business layer; `application/ouroboros/README.md` documents the framework. `VERSIONS.md` at the git root is the single source of truth for versions and cross-project boundaries.

> **Docs were realigned to the current repository layout on 2026-10-14.** Overall project docs live directly under `documentation/`; each subproject's documents live under `documentation/<project>/`. If you find a lingering `smartagent-core`, `build_graph`, `run_agent`, or `application/smartagent/` reference, it is a miss unless clearly marked as historical.

## The framework package was renamed: `src` → `ouroboros`

Framework 2.0.0 renamed its import package. `import src.…` no longer works anywhere; it is **`from ouroboros.… import …`**.

This was not cosmetic. The distribution `ouroboros` used to ship a top-level import package literally named `src` (`packages = [{ include = "src" }]`), while the business layer is itself src-layout. With the host root on `sys.path`, `import src` **silently** bound to the host's own namespace package — the same file got double-addressed as both `smartagent.db.models` and `src.smartagent.db.models`, giving two `@lru_cache`d `Settings` singletons and two `DeclarativeBase` registries. It also contradicted the framework's own frozen contract (`ouroboros/CHANGELOG.md` v1.0.0 promised a top-level `ouroboros`). Public API symbols were untouched — only the package prefix changed.

Consequence worth knowing: `backend/tests/conftest.py` **no longer needs any framework `sys.path` injection**. It only inserts the business layer's own `src/`. Do not re-add a `CORE_SRC` line.

## Build and test

Both projects target **Python 3.11–3.14** (`<3.15` is deliberate — no released `litellm` admits 3.15, and the framework's compatibility matrix is frozen at 3.11–3.14). `langgraph` was dropped from both projects; it was declared but never imported.

```bash
# Framework
cd application/ouroboros && poetry install && poetry run pytest -q     # 168 tests

# Business layer
cd application/platformagent/backend && poetry install && poetry run pytest -q   # 79 tests
```


## The two-layer architecture (read this before changing behavior)

The core idea is **Ports & Adapters with a strict dependency direction**:

```
api → services → adapters → ouroboros (ports)
```

- `ouroboros` owns the agent loop (`Plan → Decide → Execute → Observe`), the plugin/skill/tool protocols, and memory mechanics. Its single entry point is `AgentRuntime.run(...)` / `.resume(...)` in `ouroboros/ouroboros/core/runtime.py`.
- `ouroboros` defines **ports** (`ouroboros/ouroboros/ports.py`: `LLMGateway`, `Embedder`, `Plugin`, `PermissionChecker`, `WorkingMemory`, `LongTermMemory`, `Knowledge`/`Retriever`, `EventSink`, `Judge`, `Metrics`, `Checkpointer`); the business layer implements host-side ports as **adapters** (`platformagent/backend/src/smartagent/adapters/`) and composes documented framework modules such as gateways, registries, and memory. It must not depend on private `core` node/state implementations. The framework never imports the business layer.
- `backend/src/smartagent/api/` is HTTP semantics only; `services/` orchestrates (assembles a framework run and folds the result back into DB/memory/audit); `adapters/` bridge the two; `db/` (ORM) and `iam/` (RBAC) are shared.

The framework is **not** just a library you call — the business layer exists to get a handful of subtle framework contracts right. They are documented in three places and matter before touching `services/run_service.py`:

1. `backend/src/smartagent/services/run_service.py` module docstring (three silent-bug contract details: working-memory write ordering, host-side recall vs `deps.long_term_memory`, and resume re-running the paused `execute` step).
2. `documentation/platformagent/业务层详细设计.md` §4 (six runtime integration contracts, including working-memory write ordering, recall behavior, resume replay, per-run model routing/cost attribution, and database session concurrency).
3. `application/platformagent/backend/README.md` §"Two layers, one repository".

The sub-agent cycle is broken by injecting a bound method (`RunService._run_child`) into `DbSubagentRunner` at construction time; adapters must never import `services`.

## Commands

All business-layer commands run from `application/platformagent/backend/` (Poetry `in-project = true` per `poetry.toml`, so the venv lives at `backend/.venv`).

**Business layer** (`application/platformagent/backend/`):

```bash
docker compose up -d                          # PostgreSQL+pgvector, Redis only (no app service)
cp .env.example .env                          # then fill DEEPSEEK_API_KEY
poetry install                                # also installs ouroboros (2.0.0) as an editable path dep
poetry run alembic upgrade head               # 4 revisions, 22 tables + role/permission/admin seed
poetry run uvicorn smartagent.main:app --reload
poetry run pytest -q                          # 79 tests, no PostgreSQL/Redis/LLM needed
poetry run pytest tests/test_api.py -q        # single file
poetry run pytest -k "approve" -q             # filter by test name
```

Interactive API docs (Scalar) at `GET /docs`; health at `GET /health`.

**Framework layer** (`application/ouroboros/`):

```bash
poetry install
poetry run pytest          # 168 tests, no external deps (Redis/LLM/DB all faked)
```

**Console** (`application/platformagent/frontend/`):

```bash
npm install
npm run dev                # Vite dev server; proxies /v1 to 127.0.0.1:8000
```

**Capability Registry** (`application/capability/`):

```bash
docker compose up --build            # db + backend (8000) + frontend (3000)
# or, for local dev: docker compose up -d db, then run backend (uvicorn app.main:app) and frontend (npm run dev) separately

backend/.venv/Scripts/python mock-server/server.py   # real FastMCP server, streamable HTTP on :9000
# then sync a provider at http://localhost:9000/mcp
```

Note the two compose files target the same host ports (Postgres 5432, backend 8000) with different credentials/db names (`smartagent` vs `registry`) — don't run both stacks at once without adjusting ports.

## Configuration

Every knob is a field on `smartagent.config.Settings` (pydantic-settings) and is overridable by an upper-cased env var of the same name; `.env.example` lists them all and is unusually well annotated — read it for rationale. The behavior-changing ones:

- `AUTH_ENABLED=false` bypasses JWT and returns a system **admin** principal — which also disables the HITL approval path (admins are allowed outright by `check_permission`).
- `LLM_ROUTING_ENABLED` + `LLM_CHEAP_MODEL`/`LLM_EXPENSIVE_MODEL` route agents that pinned no `config.model` by task complexity; an agent that *did* set a model keeps it.
- `JUDGE_MODEL` is kept separate from the business model so evaluation scores stay comparable; it bypasses routing and caching by design.
- `EVAL_SWEEP_ON_STARTUP=false` skips the startup sweep of interrupted evaluations (tests rely on this).
- `BOOTSTRAP_ADMIN_PASSWORD` is read **only at migration time, and only for a fresh database**; empty falls back to the well-known `admin123`.

## Conventions and gotchas

- **Primary keys are minted in the app, not the DB**: `util.new_id` produces `{prefix}_{uuid4hex}` (`agent_`, `run_`, `step_`, `mem_`, `eval_`, `exp_`, …). The framework's `id_gen` is pointed at this so framework-minted ids follow the same convention.
- **`runs` / `run_steps` are the source of truth.** The Redis "Working Brain" is a volatile cache; anything auditable goes to PostgreSQL.
- **Multi-tenancy is a hard line.** Every query filters on `tenant_id`; a cross-tenant resource returns 404 (never 403, which would leak existence).
- **Tests use no real database on purpose.** Models use `JSONB` and pgvector `Vector`, which SQLite can't compile; `backend/tests/conftest.py` provides a `FakeSession` (understands `select(...).where(...).order_by(...)`), a `MockLLMGateway`, `FakeMemoryManager`, and disables rate limiting + the startup sweep. (`FakeBrain` and `DeleteAccountTool` remain defined but are now unused — `FakeBrain` was superseded by `FakeMemoryManager`.) Business tests deliberately do not re-test the agent loop — `ouroboros/tests/` covers that.
- **Adding an endpoint means touching three layers**: router in `api/routes/`, schema in `api/schemas.py`, and registration in `main.py` (15 routers are listed explicitly there — there is no auto-discovery).
- **`runs.cost` is only meaningful from 0.3.0 onward** (the column predates any writer, so older runs report 0; `RunOut` now returns `cost` and `model`).
- **Capability Registry is deployment-separate from the business layer.** It stores Tool manifests and executes MCP/API calls behind its own HTTP service; Platform loads these as standard runtime Tools through the shared-key-protected internal API. The MCP sync path uses `initialize` + `tools/list`. Management APIs have no user auth, CORS is `*`, and `auto_create_tables` is on by default. `ouroboros` has its own unrelated partial MCP client (`ouroboros/ouroboros/tools/mcp.py`, JSON-RPC over streamable HTTP, no `tools/list`).

## Project status

Per `VERSIONS.md` (the single source of truth), `documentation/platformagent/版本规划.md`, and `backend/README.md`: the platform line is **0.3.0** — 0.1.0 (skeleton) and 0.2.0 (plugins/IAM/memory) are closed, and 0.3.0 (evaluation + A/B + cost attribution, plus checkpoint persistence and Capability HTTP integration) is delivered. **0.4.0** (knowledge/reliability) and **0.5.0** (production/observability, incl. the Playground) are not started. The framework is at **2.0.0** (package renamed `src`→`ouroboros`) and its `__all__` symbol surface is frozen since 1.0.0; the business layer's first priority when the framework changes is to keep up with the ports contract.

The Capability Registry is at **v0.3.0** with its roadmap in `documentation/capability/version-roadmap.md`: local Tool CRUD, MCP Provider sync, API Services/API Tools, and Platform runtime integration are implemented; Discovery and permission enforcement remain planned. Its host ports are **5433 / 8010 / 3010** so both compose stacks can run at once. Platform integration is HTTP-only; there is no shared Python package or database.

The React console is a thin UI over the business API. A backend is required to log in; demo fallback applies only after a token is already stored, and only for the Agents/Runs lists.
