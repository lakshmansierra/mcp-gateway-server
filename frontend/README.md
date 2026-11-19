# MCP Gateway UI

React (Vite) admin console for registering and managing MCP servers behind the gateway.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build in dist/
```

## Access

- **Admin Portal**: demo credentials `admin` / `admin123` (see `src/context/AuthContext.jsx`). Admins can add, enable/disable, remove, restore and permanently delete MCP servers.
- **User Access**: no login; view the dashboard and server list (admin gateway keys hidden), select one or more active MCP servers and generate a single gateway API (endpoint + API key + client config) for them.

## Pages

| Route | Who | Purpose |
|---|---|---|
| `/` | all | Choose Admin or User access |
| `/login` | all | Admin login |
| `/dashboard` | admin, user | Server counts, servers by transport, recently added |
| `/mcp-servers` | admin, user | Server list; admins get **+** to add and trash to remove |
| `/deleted-servers` | admin | Soft-deleted servers: restore or delete permanently |
| `/gateway-apis` | user | Generated gateway APIs: view client config, copy key, revoke |

## Backend

All data goes through `src/services/mcpService.js`, which currently stores servers in `localStorage`.
Replace the function bodies with `fetch()` calls to your gateway API to connect a real backend.

Generated user APIs use `VITE_GATEWAY_BASE_URL` (default `https://mcp-gateway.example.com`) to build endpoints of the form
`<base>/v1/gateway/<id>/mcp`. Backend equivalent of `generateGatewayApi`: `POST /api/gateway-apis { name, serverIds }`.

## Deploy to Cloud Foundry

The app is a static build served by the CF `staticfile_buildpack` (nginx).

| File | Purpose |
|---|---|
| `manifest.yml` | App name, memory, buildpack; pushes only `dist/` |
| `public/Staticfile` | Copied into `dist/` on build. `pushstate: enabled` serves `index.html` for deep links like `/mcp-servers`; forces HTTPS + HSTS |
| `.env.production` | Build-time settings (`VITE_GATEWAY_BASE_URL`) |

```bash
# 1. Set the real gateway URL in .env.production, then build
npm ci
npm run build

# 2. Log in and push (from the project root, where manifest.yml is)
cf login -a <api-endpoint>
cf target -o <org> -s <space>
cf push
```

Notes:
- `VITE_*` values are baked in at build time: change `.env.production` and rebuild + push to update them.
- Check the buildpack exists in your landscape with `cf buildpacks`. If only `nginx_buildpack` is available, it needs an `nginx.conf` in `dist/` instead of `Staticfile`.
- Data is still stored in each browser's localStorage until `src/services/mcpService.js` is wired to the gateway backend.
