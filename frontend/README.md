# MCP Gateway UI

React (Vite) console for the MCP Gateway backend (FastAPI + SAP HANA): register MCP servers, manage users, and generate gateway API keys.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build in dist/
```

## Configuration

URLs are baked in at build time: `.env` (local, git-ignored; copy `.env.example`) for `npm run dev`, and
`.env.production` (deployed URLs) for `npm run build`, which overrides `.env`.

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL, e.g. `https://mcp-gateway-backend.<cf-domain>`. The backend's `BACKEND_CORS_ORIGINS` must include this UI's origin. |
| `VITE_GATEWAY_MCP_URL` | The gateway's MCP endpoint shown in client configs, e.g. `https://mcp-gateway-server.<cf-domain>/mcp/gateway` |

## Access

- **Admin Portal** (`/login` → `POST /api/admin/login`): admins manage MCP servers, tools, users, API keys and see tool usage.
- **User Access** (`/user-login` → `POST /api/user/login`): users (created by an admin) see the servers and tools they
  can use, generate API keys and see their own usage.

The login token is kept in `sessionStorage` and sent as `Authorization: Bearer`. On page load the account is refreshed
with `GET /api/me`. A 401 from the backend, or the token's expiry, ends the session.

## Pages

| Route | Who | Backend endpoints |
|---|---|---|
| `/dashboard` | admin | `GET /api/health`, `/api/admin/servers`, `/api/admin/keys`, `/api/admin/users`, `/api/admin/usage` |
| `/mcp-servers` | admin | `GET /api/admin/servers` (live ones), `POST`, `PATCH /{id}`, `DELETE /{id}` |
| `/mcp-servers/:id` | admin | `GET /api/admin/servers/{id}`, `GET …/{id}/tools`, `GET /api/admin/usage?server_id=`; Visible / Hidden per tool edits `include_tools` / `exclude_tools` with `PATCH /api/admin/servers/{id}` |
| `/deleted-servers` | admin | `GET /api/admin/servers` (`is_deleted`), `POST /api/admin/servers/{id}/restore` |
| `/tools` | admin | `GET /api/admin/tools`, `GET /api/admin/tools/{id}/changes` (history), `GET /api/admin/usage` |
| `/tools` | user | `GET /api/user/servers`, `GET /api/user/tools`, `GET /api/user/usage` |
| `/users` | admin | `GET /api/admin/users`, `GET /api/admin/users/{id}` (with keys), `POST`, `DELETE /{id}`, `POST …/restore`, `PATCH …/password` |
| `/gateway-apis` | admin | `GET /api/admin/keys`, `POST /api/keys`, `DELETE /api/admin/keys/{id}`, `POST …/restore`, `POST …/rotate`, `PATCH …/servers` |
| `/gateway-apis` | user | `GET /api/user/keys`, `GET /api/user/servers` (to pick servers), `POST /api/keys` |
| `/usage` | admin | `GET /api/admin/usage`, `GET /api/admin/usage/calls` (filters: dates, server, account, status; paged) |
| `/usage` | user | `GET /api/user/usage`, `GET /api/user/usage/calls` (filters: dates, server, key, status; paged) |
| Account (top-right menu) | admin, user | `PATCH /api/me/password`, `POST /api/me/logout-all`; log out uses `POST /api/me/logout` |

`POST /api/admin/register` is intentionally not part of the UI.

All API calls live in `src/services/mcpService.js` (on top of the HTTP client in `src/services/api.js`); pages load
data with the `useLoader` hook (`src/hooks/useLoader.js`). Admin lists include deleted rows, tagged; user pages never
show anything deleted or removed. Plain API keys are shown once, after create or rotate.

## Deploy to Cloud Foundry

The app is a static build served by the CF `staticfile_buildpack` (nginx).

| File | Purpose |
|---|---|
| `manifest.yml` | App name, memory, buildpack; pushes only `dist/` |
| `public/Staticfile` | Copied into `dist/` on build. `pushstate: enabled` serves `index.html` for deep links like `/mcp-servers`; forces HTTPS + HSTS |
| `.env.production` | Build-time settings (`VITE_API_BASE_URL`, `VITE_GATEWAY_MCP_URL`) |

```bash
npm ci
npm run build
cf login -a <api-endpoint>
cf target -o <org> -s <space>
cf push
```

`VITE_*` values are baked in at build time: change `.env.production`, then rebuild and push.
