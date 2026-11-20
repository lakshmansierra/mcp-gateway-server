# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP gateway: one authenticated Streamable HTTP endpoint that aggregates many upstream MCP servers. Four independently deployable parts share one repo:

- `mcp_gateway/` – the gateway itself (Python, official `mcp` SDK + Starlette). Deployed to Cloud Foundry.
- `backend/` – FastAPI admin/user API that manages servers, users and API keys in SAP HANA. Deployed to Cloud Foundry.
- `frontend/` – React + Vite admin console (static build, CF `staticfile_buildpack`).
- `servers/`, `clients/` – sample upstream MCP servers and sample clients (plain MCP client + GPT-4.1 agents via SAP Gen AI Hub) for local testing.

Each part has its own `.env` (`mcp_gateway/.env`, `backend/.env`, `clients/.env`, copied from the `.env.example` next to it), its own `requirements.txt`/`runtime.txt`, `manifest.yml` and `.cfignore`. There is no root `requirements.txt` despite the README; install `mcp_gateway/requirements.txt` (superset, includes the backend's deps) into the root `.venv`.

There are no tests, linters or formatter configs in the repo.

## Commands

```bash
# Gateway (port 8080, path from GATEWAY_PATH; deployed value is /mcp/gateway)
python mcp_gateway/main.py [--env-file PATH] [--transport http|stdio] [--host H] [--port P]

# Backend (port 8000, OpenAPI docs at /docs)
python backend/main.py
uvicorn backend.main:app --port 8000 --reload     # from repo root

# Sample upstream servers (ports 9001, 9002, 9003; server_5 serves both /mcp and /sse)
python servers/server_1/server_1.py

# Sample clients
python clients/client_1/client.py

# Frontend
cd frontend && npm install && npm run dev        # http://localhost:5173
cd frontend && npm run build

# Deploy (from inside the part's folder, where its manifest.yml is)
cf push
```

For a local end-to-end run: start sample servers, register them via the backend (`POST /api/admin/servers`, e.g. `server_1` → `http://127.0.0.1:9001/mcp`), create a key (`POST /api/keys`), then start the gateway and a client.

## Import / packaging convention

Both Python apps import themselves by package name (`mcp_gateway.*`, `backend.*`) but must also run as plain scripts. `mcp_gateway/main.py` and `backend/main.py` fix up `sys.path` at the top (the gateway also *removes* its own folder so its `config/`, `auth/`, `db/` subpackages can't shadow third-party modules). On CF, the `command` in each `manifest.yml` symlinks `$HOME` to `/tmp/pkg/<package>` and puts `/tmp/pkg` on `PYTHONPATH` for the same reason. Keep imports absolute (`from mcp_gateway.x import ...`).

## Architecture

**HANA is the source of truth and the integration point between backend and gateway.** The backend writes servers / users / API keys / key→server mappings; the gateway only *reads* those tables (reloading every `GATEWAY_DB_SYNC_INTERVAL`, and immediately when the backend hits the gateway's `GATEWAY_RELOAD_PATH` with `GATEWAY_RELOAD_SECRET` — see `backend/gateway_notify.py`, a middleware that fires after any successful write). The gateway writes only its own usage tables (`tools_mgs`, `tool_changes_mgs`, `tool_calls_mgs`). No table DDL exists in the repo; table names come from env vars (`*_TABLE`, see README).

**Gateway request flow** (`mcp_gateway/`):
- `web/app.py` – Starlette app: MCP endpoint, unauthenticated `/health`, internal reload route.
- `auth/api_keys.py` – ASGI middleware: SHA-256 hashes the presented key (`Authorization: Bearer` or `X-API-Key`), looks it up in the in-memory registry, and scopes which upstreams the caller may see.
- `server/gateway.py` – MCP handlers. List requests are served from an in-memory **catalog**; calls/reads/prompts are routed live to the owning upstream. Tools and prompts are namespaced `<server_name>__<name>`; resources keep their URIs and are routed by ownership.
- `upstream/pool.py` – one supervisor per upstream: connect, 30s health check, exponential-backoff reconnect, catalog cache, `subscriptions/listen` change streams with debounce, include/exclude tool filtering. **Per-client sessions**: each API key gets its own upstream session (identified by `X-MCP-Client: <user>/<key>`), closed after `GATEWAY_CLIENT_SESSION_IDLE`.
- `db/` – loads the registry from HANA; `db/usage.py` + `usage/recorder.py` buffer tool lists/calls in memory and flush to HANA in the background (never blocks a call).
- `config/settings.py` – the only place settings are read; the gateway reads *only* `GATEWAY_*` and HANA-related variables.

Key-scope rules (enforced in the gateway's registry loading, mirrored by backend ownership rules): admin keys (`all_servers = 1`) reach every server *that admin registered*, enabled or not; user keys (`all_servers = 0`) reach only mapped, enabled servers registered by the admin who created that user. Deleted keys/owners stop working.

Because client sessions live in memory, the gateway runs as a single CF instance (or needs sticky sessions on `Mcp-Session-Id`).

**Backend layering** (`backend/`): `routes/` (FastAPI routers under `/api/admin`, `/api/user`, `/api/me`, `/api/keys`, `/api/admin/keys`, `/api/admin/servers`) → `services/` (business rules; `services/ownership.py` defines what an admin may manage: their own items plus those of users they created) → `db/` (raw `hdbcli` SQL, one connection per request via `Depends(get_db)`). Auth is JWT (`security.py`, `auth.py`) with revocation via `revoked_tokens` table; admin registration is gated by `ADMIN_REGISTER_KEY`. Pydantic models live in `models/`.

**Frontend** (`frontend/`): not yet wired to the backend. All data goes through `src/services/mcpService.js`, which stores to `localStorage`; demo admin login lives in `src/context/AuthContext.jsx`. `VITE_*` values in `.env.production` are baked in at build time.

## Gotchas

- CF manifests set all settings via `env:` (the `.cfignore` files keep `.env` out of the push); keep them in step with the local `.env` when adding a setting.
- CF health checks are `port`, deliberately not `/health` or `/api/health`, so an upstream or HANA outage doesn't make CF restart the app.
- Gateway logs go to stderr so stdio transport isn't corrupted — never `print()` to stdout in gateway code.
