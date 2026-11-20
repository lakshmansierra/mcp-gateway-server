# MCP Gateway UI

React (Vite) console for the MCP Gateway backend (FastAPI + SAP HANA): register MCP servers, manage users, and generate gateway API keys.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build in dist/
```

## Configuration

Set at build time (`.env.development` for `npm run dev`, `.env.production` for `npm run build`):

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL, e.g. `https://mcp-gateway-backend.<cf-domain>`. The backend's `BACKEND_CORS_ORIGINS` must include this UI's origin. |
| `VITE_GATEWAY_MCP_URL` | The gateway's MCP endpoint shown in client configs, e.g. `https://mcp-gateway-server.<cf-domain>/mcp/gateway` |

## Access

- **Admin Portal** (`/login` → `POST /api/admin/login`): admins manage MCP servers, users and API keys.
- **User Access** (`/user-login` → `POST /api/user/login`): users (created by an admin) generate API keys for servers their admin registered.

The login token is kept in `sessionStorage` and sent as `Authorization: Bearer`. A 401 from the backend, or the token's expiry, ends the session.

## Pages

| Route | Who | Backend endpoints |
|---|---|---|
| `/dashboard` | admin | `GET /api/health`; server counts |
| `/mcp-servers` | admin | `POST /api/admin/servers`, `PATCH /api/admin/servers/{id}`, `DELETE /api/admin/servers/{id}` |
| `/deleted-servers` | admin | `POST /api/admin/servers/{id}/restore` |
| `/users` | admin | `POST /api/admin/users`, `DELETE /api/admin/users/{id}`, `POST /api/admin/users/{id}/restore`, `PATCH /api/admin/users/{id}/password` |
| `/gateway-apis` | admin, user | `POST /api/keys`; admins also `DELETE /api/admin/keys/{id}`, `POST …/restore`, `POST …/rotate`, `PATCH …/servers` |
| Account (sidebar ⚙) | admin, user | `PATCH /api/me/password`, `POST /api/me/logout-all`; log out uses `POST /api/me/logout` |

`POST /api/admin/register` is intentionally not part of the UI.

All API calls live in `src/services/mcpService.js` (on top of the HTTP client in `src/services/api.js`).

## Limitation: no list endpoints

The backend has no `GET` endpoints for servers, keys or users. The tables are therefore built from the backend's
responses to actions taken in this browser, stored per account in `localStorage` (`src/services/registry.js`).
Servers, keys or users created elsewhere (another browser, Swagger, another admin) don't appear. For keys you
didn't create here, admins can use **Manage Key by ID**. Users need the server IDs from their admin to create a key.
Plain API keys are never stored: they're shown once, after create or rotate.

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
