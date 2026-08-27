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
VITE_API_BASE=http://localhost:8000/v1
```

The login screen stores the entered bearer token in local browser storage. Without a working
backend, the console remains usable with demo data so the interaction design can be reviewed.