# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

The git root holds two top-level directories:

- `application/` — all runnable code. This is itself a Poetry project (`smartagent`) that vendors two more projects as sub-directories.
- `documentation/` — design docs, written in Chinese (`技术方案设计.md`, `核心设计图.md`, `版本规划.md`, plus `业务/` and `agent/` subfolders).

Inside `application/` there are four independent pieces:

| Path | What it is |
|---|---|
| `smartagent/` | **Business layer** — FastAPI service (Python 3.11–3.14, SQLAlchemy 2.0 async, Pydantic v2, PostgreSQL+pgvector, Redis); code under `src/smartagent/`. |
| `ouroboros/` | **Framework layer** — business-agnostic agent runtime, vendored as an editable path dependency and its own nested git repo. |
| `frontend/` | React/Vite control console (`smartagent-console`) that talks to the business API. |
| `CapabilityRegistry/` | A separate new service (FastAPI + Ant Design React) that registers Tool manifests (JSONB) and syncs them from external MCP servers; own `docker-compose.yml` + a `mock-server/` MCP test target. |

`application/smartagent/README.md` is the authoritative guide to the business layer — read it first. `ouroboros/README.md` documents the framework.

## The two-layer architecture (read this before changing behavior)

The core idea is **Ports & Adapters with a strict dependency direction**:

```
api → services → adapters → ouroboros (ports)
```

- `ouroboros` owns the agent loop (`Plan → Decide → Execute → Observe`), the plugin/skill/tool protocols, and memory mechanics. Its single entry point is `AgentRuntime.run(...)` / `.resume(...)` in `ouroboros/src/core/runtime.py`.
- `ouroboros` defines **ports** (`ouroboros/src/ports.py`); the business layer implements them as **adapters** (`smartagent/src/smartagent/adapters/`) and never imports framework internals. The framework never imports the business layer.
- `smartagent/src/smartagent/api/` is HTTP semantics only; `services/` orchestrates (assembles a framework run and folds the result back into DB/memory/audit); `adapters/` bridge the two; `db/` (ORM) and `iam/` (RBAC) are shared.

The framework is **not** just a library you call — the business layer exists to get a handful of subtle framework contracts right. They are documented in three places and matter before touching `services/run_service.py`:

1. `smartagent/src/smartagent/services/run_service.py` module docstring (three silent-bug contract details: working-memory write ordering, host-side recall vs `deps.long_term_memory`, and resume re-running the paused `execute` step).
2. `documentation/业务/业务层详细设计.md` §0 ("contract details").
3. `application/smartagent/README.md` §"Two layers, one repository".

The sub-agent cycle is broken by injecting a bound method (`RunService._run_child`) into `DbSubagentRunner` at construction time; adapters must never import `services`.

## Commands

All business-layer commands run from `application/smartagent/`. Poetry is configured with `in-project = true` (`poetry.toml`), so the venv lives at `application/smartagent/.venv`.

**Business layer** (`application/smartagent/`):

```bash
docker compose up -d                          # PostgreSQL+pgvector, Redis (the app's infra)
cp .env.example .env                          # then fill DEEPSEEK_API_KEY
poetry install                                # also installs ouroboros as editable path dep
poetry run alembic upgrade head               # 4 revisions, 22 tables + role/permission/admin seed
poetry run uvicorn smartagent.main:app --reload
poetry run pytest -q                          # ~67 tests, no PostgreSQL/Redis/LLM needed
poetry run pytest tests/test_api.py -q        # single file
poetry run pytest -k "approve" -q             # filter by test name
```

Interactive API docs (Scalar) at `GET /docs`; health at `GET /health`.

**Framework layer** (`application/ouroboros/`):

```bash
poetry install
poetry run pytest          # ~168 tests, no external deps (Redis/LLM/DB all faked)
```

**Console** (`application/frontend/`):

```bash
npm install
npm run dev                # Vite dev server; proxies /v1 to 127.0.0.1:8000
```

**Capability Registry** (`application/CapabilityRegistry/`):

```bash
docker compose up --build            # db + backend (8000) + frontend (3000)
# or, for local dev: docker compose up -d db, then run backend (uvicorn app.main:app) and frontend (npm run dev) separately

# mock MCP server (real FastMCP server, streamable HTTP on :9000) — sync a provider at http://localhost:9000/mcp:
backend/.venv/Scripts/python mock-server/server.py
```

Note the two compose files target the same host ports (Postgres 5432, backend 8000) with different credentials/db names (`smartagent` vs `registry`) — don't run both stacks at once without adjusting ports.

## Configuration

Every knob is a field on `smartagent.config.Settings` (pydantic-settings) and is overridable by an upper-cased env var of the same name; `.env.example` lists them all. The behavior-changing ones:

- `AUTH_ENABLED=false` bypasses JWT and returns a system **admin** principal — which also disables the HITL approval path (admins are allowed outright).
- `LLM_ROUTING_ENABLED` + `LLM_CHEAP_MODEL`/`LLM_EXPENSIVE_MODEL` route agents that pinned no `config.model` by task complexity; an agent that *did* set a model keeps it.
- `JUDGE_MODEL` is kept separate from the business model so evaluation scores stay comparable.
- `EVAL_SWEEP_ON_STARTUP=false` skips the startup sweep of interrupted evaluations (tests rely on this).

## Conventions and gotchas

- **Primary keys are minted in the app, not the DB**: `util.new_id` produces `{prefix}_{uuid4hex}` (`agent_`, `run_`, `step_`, `mem_`, …). The framework's `id_gen` is pointed at this so framework-minted ids follow the same convention.
- **`runs` / `run_steps` are the source of truth.** The Redis "Working Brain" is a volatile cache; anything auditable goes to PostgreSQL.
- **Multi-tenancy is a hard line.** Every query filters on `tenant_id`; a cross-tenant resource returns 404 (never 403, which would leak existence).
- **Tests use no real database on purpose.** Models use `JSONB` and pgvector `Vector`, which SQLite can't compile; `smartagent/tests/conftest.py` provides a `FakeSession` and disables rate limiting + the startup sweep.
- **`langgraph` is still declared in `pyproject.toml` but unused** — the framework replaced the graph loop with its own `AgentRuntime`. Safe to drop at the next dependency cleanup.
- `runs.cost` is only meaningful from V1.1 onward (the column predates any writer).

## Project status

Per `documentation/版本规划.md` and `application/smartagent/README.md`: V0.1 (skeleton) and V0.2 (plugins/IAM/memory) are closed, V1.1 (evaluation + cost) is delivered; V0.3 (knowledge/reliability) and V1.0 (production/observability) are **not started**. The Capability Registry is a parallel effort: v0.1 Tool CRUD and v0.2 MCP Provider sync are implemented (the backend is an MCP **client** — `initialize` + `tools/list` only, it never `tools/call`); discovery (`/discover`), catalog, and permission enforcement are still missing. Its MCP half is metadata-only: it stores tool manifests but never executes tools. ouroboros has its own partial MCP client (`McpTool`, `ouroboros/src/tools/mcp.py` — streamable HTTP only, per-call `initialize`, no `tools/list`), but nothing assembles Registry manifests into runtime plugins yet (the roadmap assigns `db_plugin_loader` to the host layer). The React console is a thin UI over the business API and falls back to demo data when the backend is unreachable.
