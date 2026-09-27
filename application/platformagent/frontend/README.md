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

The login screen posts username and password to `POST /v1/auth/login` and stores the returned
bearer token in local browser storage. Bootstrap account is `admin` / `admin123` unless
`BOOTSTRAP_ADMIN_PASSWORD` was set. Tenant is optional and only needed when the same username
exists in more than one tenant. Without a working backend, the console remains usable with demo
data so the interaction design can be reviewed.