# SmartAgent Console

React/Vite control console for the SmartAgent API.

## Run

```bash
npm install
npm run dev
```

The dev server proxies `/v1` to `http://localhost:8000`. To use another address, create
`.env.local` with:

```bash
VITE_API_BASE=http://127.0.0.1:8000/v1
```

For the containerized full stack, run `docker compose up --build -d` from
`application/platformagent/backend`. The production console is served at
`http://localhost:3000` and proxies API/SSE requests to the backend container.

The login screen posts username and password to `POST /v1/auth/login` and stores the returned
bearer token in local browser storage. Bootstrap account is `admin` / `admin123` unless
`BOOTSTRAP_ADMIN_PASSWORD` was set. Tenant is optional and only needed when the same username
exists in more than one tenant.

## Demo data

A backend is **required to log in** — `login()` has no fallback, so without one the console stops
at the login screen. Demo fallback applies only after a valid token is already in local storage:
if `GET /v1/agents` then fails, the Agents/Runs lists keep their built-in sample rows and a
"后端暂不可用，当前显示演示数据" notice is shown. `GET /v1/tools` and `GET /v1/skills` failures are
swallowed silently and leave those lists empty.
