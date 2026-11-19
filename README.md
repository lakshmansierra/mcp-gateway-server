# mcp-gateway-server

A single MCP endpoint for all AI clients. The gateway connects to every live MCP
server listed in `mcp_gateway/.env` and exposes their tools, resources and prompts
through one authenticated URL. Clients don't connect to upstream servers directly.

```
 Claude / Cursor / VS Code / custom agents
                 │  Authorization: Bearer <api key>
                 ▼
        ┌──────────────────┐
        │   MCP Gateway    │  /mcp     Streamable HTTP endpoint
        │                  │  /health  upstream status (no auth)
        └──────────────────┘
          │       │       │   Streamable HTTP or SSE
          ▼       ▼       ▼
       github   docs    crm  ...   (live MCP servers)
```

## Features

- **Aggregation.** Tools and prompts from every server appear as `<server>__<name>`
  (for example `server_1__add`). Resources keep their original URIs, and the
  gateway routes each read to the server that owns the URI.
- **API-key auth.** Clients send `Authorization: Bearer <key>` or `X-API-Key: <key>`.
  You can limit a key to certain upstreams with glob patterns.
- **Per-client identity.** Each client key gets its own session to each server, sent with
  `X-MCP-Client: <key name>` (for example `admin`, `group_1`). So servers see
  which client is calling, and no session state is shared between clients. Sessions open on
  first use and close after 5 idle minutes; `/health` lists the open ones per server. The
  sample servers' `whoami` tool shows it.
- **Instant catalog updates.** The gateway listens to each server's change stream
  (`subscriptions/listen`). When tools, resources or prompts change, it re-lists that server
  about 1s later. Servers that can't stream changes are re-listed every 30s. Clients can open
  their own `subscriptions/listen` stream to the gateway, and each change is announced only
  to clients whose key may use that server. A server going down or coming back counts as a change too.
- **Tool filtering.** Each upstream has `_INCLUDE_TOOLS` / `_EXCLUDE_TOOLS` lists of full tool
  names, so you can hide dangerous tools (for example `delete_everything`).
- **Resilience.** Each upstream has its own supervisor that health-checks the connection
  every 30s and reconnects with exponential backoff. If one upstream is down, the
  others keep working, and calls to the down server get a clear error.
- **Tool usage in HANA.** Every server's tools and how they change over time, and every tool call
  (who, when, how long, ok / error / timeout), are written to three HANA tables in the background.
  See [Tool usage](#tool-usage).
- **Configured by environment variables.** Settings come from a `.env` file or the real environment.
- **Transports.** HTTP for remote clients; stdio for local clients that launch the gateway as a subprocess.

## How the catalog works

The gateway keeps a **catalog** in memory: the tools, resources, resource templates and
prompts of every connected server. List requests (`tools/list`, `resources/list`,
`prompts/list`) are answered from the catalog. Calls (`tools/call`, `resources/read`,
`prompts/get`) always go to the live server.

```
tools/list  → catalog in memory (re-fetched first if older than 30s) → reply
tools/call  → the server that owns the tool, every time              → reply
```

**What the catalog is for**

- **Fast lists.** A list comes from memory in about a millisecond, however many servers are behind the gateway.
- **Routing.** The catalog tells the gateway which server owns a tool or a resource URI, and
  whether include/exclude filters allow it, without asking the servers first.
- **Change detection.** Each refresh compares the new catalog with the old one, so the gateway
  knows what changed and can notify only the clients that are allowed to see it.
- **Down servers.** When a server disconnects, its entries are removed once. Clients get a
  clean list instead of each request waiting on a dead server.

**Why lists don't ask every server on demand**

If the gateway asked every server on each `tools/list`, it would work, but it would be slower and heavier:

```
on demand:  client → gateway ─┬→ server_1  50 ms ─┐
                              ├→ server_2  80 ms  ├→ reply after 2 s (the slowest server)
                              └→ server_4   2 s  ─┘
catalog:    client → gateway → memory → reply in about 1 ms
```

- **The slowest server sets the speed.** Each list waits for every server, so one slow or
  overloaded server slows the list for every client.
- **Load grows with clients.** AI clients ask for lists often (on connect, on reconnect,
  sometimes every turn). With 50 clients and 4 servers, each round sends 200 identical
  requests to the servers. With the catalog, each server is asked about once per 30s,
  however many clients there are.
- **Failures cost every client.** A down server would make every list request wait for a timeout.

**Why 30 seconds**

Most updates don't wait for the timer. The catalog is refreshed when the gateway connects to a
server, about 1s after a server announces a change, and when a server goes down or comes back.
The 30s refresh is a backup for servers that change without announcing it. It is a trade-off:

| Refresh interval | Effect |
|---|---|
| 0s (always ask) | always exact; slow lists and heavy load on servers |
| **30s** | a silent change shows up within 30s; each server gets about 2 list requests per minute |
| 5 min | very light load; a silent change can stay hidden for minutes |

So at 30s:

- servers that announce their changes are up to date within about 1s;
- servers that don't are never more than 30s out of date;
- server load stays the same however many clients connect.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt

cp mcp_gateway/.env.example mcp_gateway/.env   # gateway: HANA (servers + API keys) + GATEWAY_*
cp clients/.env.example clients/.env           # sample clients: gateway URL, their keys, AI Core
cp backend/.env.example backend/.env           # admin/user backend: HANA, JWT
python mcp_gateway/main.py   # or: cd mcp_gateway && python main.py; --env-file <path> for another file
```

To try it locally, run the sample servers, register them in the backend (`POST /api/admin/servers`, e.g. `server_1` at
`http://127.0.0.1:9001/mcp`), then start the gateway and a client:

```bash
python servers/server_1/server_1.py    # port 9001
python servers/server_2/server_2.py    # port 9002
python servers/server_3/server_3.py    # port 9003
python mcp_gateway/main.py             # gateway on port 8080
python clients/client_1/client.py      # admin key: lists and calls tools on every server that admin registered
python clients/client_2/client.py      # GPT-4.1 agent with API_KEY_GROUP_4 (server_4 only)
python clients/client_3/client.py      # GPT-4.1 agent with API_KEY_GROUP_1 (server_1 only)
```

## Configuration

All settings are environment variables. The gateway loads them from `mcp_gateway/.env` (git-ignored);
variables already set in the real environment take precedence. See
[mcp_gateway/.env.example](mcp_gateway/.env.example) for a full example. The sample clients read
`clients/.env` and the backend reads `backend/.env`, so each part can be deployed on its own.

**Gateway:** the gateway reads only the variables below plus the HANA ones further down; nothing else, from
`.env` or the real environment. Each `GATEWAY_*` one is optional and falls back to the value in code.

| variable | fallback | meaning |
|---|---|---|
| `GATEWAY_NAME`, `GATEWAY_VERSION` | `mcp-gateway`, `1.0.0` | name and version reported to clients and servers |
| `GATEWAY_TRANSPORT` | `http` | `http` or `stdio`; the `--transport` flag overrides it |
| `GATEWAY_HOST`, `GATEWAY_PORT`, `GATEWAY_PATH` | `127.0.0.1`, `8080`, `/mcp` | where the gateway listens |
| `GATEWAY_ALLOWED_HOSTS` | empty | host:port values clients may use (DNS-rebinding protection); empty = localhost only on 127.0.0.1, any Host otherwise |
| `GATEWAY_LOG_LEVEL` | `INFO` | log detail |
| `GATEWAY_AUTH_ENABLED` | `true` | require API keys |
| `GATEWAY_RECONNECT_INITIAL_DELAY`, `GATEWAY_RECONNECT_MAX_DELAY` | `1`, `60` | reconnect backoff (seconds) |
| `GATEWAY_STARTUP_CONNECT_TIMEOUT` | `10` | seconds to wait for servers at startup |
| `GATEWAY_HEALTH_CHECK_INTERVAL` | `30` | seconds between health checks / re-lists |
| `GATEWAY_CATALOG_TTL` | `30` | seconds before a list request re-fetches the catalog |
| `GATEWAY_CHANGE_DEBOUNCE` | `1` | seconds to wait after a change notification |
| `GATEWAY_CLIENT_SESSION_IDLE` | `300` | seconds before an unused client session closes |
| `GATEWAY_DB_SYNC_INTERVAL` | `30` | seconds between re-reads of the servers and API keys in HANA |
| `GATEWAY_HEALTH_PATH` | `/health` | route that answers without an API key (health checks) |
| `GATEWAY_CLIENT_ID_HEADER` | `X-MCP-Client` | header naming the client (`<user>/<key>`) on its sessions to servers |
| `GATEWAY_RELOAD_PATH` | `/internal/reload` | route the backend calls after a change, so it applies at once |
| `GATEWAY_RELOAD_SECRET` | empty (off) | secret the backend must send to that route; same value in `backend/.env` |
| `GATEWAY_USAGE_FLUSH_INTERVAL` | `5` | seconds between writes of tool usage to HANA |
| `GATEWAY_USAGE_BUFFER_MAX` | `10000` | tool calls that may wait while HANA can't be reached; beyond that the oldest are dropped |

**Client API keys** are not set in `.env` either: they are rows of the key table in HANA, created through
the backend (`POST /api/keys`, shown once). The table stores only each key's SHA-256 hash; the gateway hashes
what a client sends (`Authorization: Bearer <key>`) and looks it up. A key works while neither it nor its
owner is deleted:

- `all_servers = 1` (admins' keys) reaches only the servers that admin registered, enabled or disabled,
  never another admin's servers;
- `all_servers = 0` (users' keys) reaches only the servers mapped to it in the mapping table, only while
  they are enabled, and only servers registered by the admin who created that user.

Put the keys the sample clients should use into `clients/.env`.

**MCP servers** are not set in `.env`: they are the rows of the server table in SAP HANA, registered,
edited and deleted through the backend. The gateway reads the servers and keys at startup (and stops if it
can't) and again every `GATEWAY_DB_SYNC_INTERVAL` seconds, so changes apply without a restart. The backend also calls the
gateway's reload route right after each change (`GATEWAY_RELOAD_URL` + `GATEWAY_RELOAD_SECRET` in
`backend/.env`), so they normally apply within about a second; the periodic re-read is the fallback:

- a new row connects; a deleted or disabled row disconnects and its tools disappear;
- a changed `server_url`, `transport` or `timeout_seconds` reconnects;
- a changed `include_tools` / `exclude_tools` re-filters the tools on the open connection;
- a new, deleted, rotated or re-mapped API key takes effect on the next re-read;
- if HANA can't be reached on a re-read, the current servers and keys stay in use.

`server_name` is the tool prefix: `server_1` gives `server_1__add`.

| variable | fallback | meaning |
|---|---|---|
| `HANA_HOST`, `HANA_USER`, `HANA_PASSWORD`, `HANA_SCHEMA` | none: required | the HANA database |
| `HANA_PORT` | `443` | HANA Cloud's SQL port |
| `HANA_CONNECT_TIMEOUT`, `HANA_QUERY_TIMEOUT` | `10`, `30` | seconds before a HANA call gives up; the next re-read retries |
| `MCP_SERVER_TABLE` | `mcp_app_mgs` | the server table |
| `MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE` | `client_to_gateway_mcp_api_key_mgs` | the key table |
| `MCP_CLIENT_TO_GATEWAY_API_KEY_MAPPING_TABLE` | `client_to_gateway_mcp_api_key_mapping_mgs` | key-to-server mapping |
| `USER_TABLE` | `user_mgs` | the users, so a deleted user's keys stop working |
| `MCP_TOOL_TABLE` | `tools_mgs` | every server's tools (the gateway writes it) |
| `MCP_TOOL_CHANGE_TABLE` | `tool_changes_mgs` | each tool's history (the gateway writes it) |
| `MCP_TOOL_CALL_TABLE` | `tool_calls_mgs` | every tool call (the gateway writes it) |

## Tool usage

The gateway only reads the server, key and user tables. It writes three tables of its own:

| table | one row per | filled when |
|---|---|---|
| `tools_mgs` | tool of a server (`mcp_id` = the server's id), ever listed | a re-list (connect, every 30s, a change the server announces) finds a new tool. A tool that disappears gets `removed_at`; one that comes back gets it cleared. Rows are never deleted. Hidden tools (`exclude_tools`) are recorded too |
| `tool_changes_mgs` | change: `added`, `removed`, `changed` | the same re-list; `changed` means a new description or input schema, and `old_value` / `new_value` hold both as JSON |
| `tool_calls_mgs` | `tools/call` | every call made with an API key: tool, key, user, `called_at` (UTC), `duration_ms`, `status` (`ok` / `error` / `timeout`), `error_message`. Arguments and results are not stored |

Nothing waits for HANA: the gateway collects usage in memory and writes it every
`GATEWAY_USAGE_FLUSH_INTERVAL` seconds. If HANA can't be reached, it keeps everything for the next round (up to
`GATEWAY_USAGE_BUFFER_MAX` calls) and calls keep working. With several gateway instances each change is
recorded once. Calls without an API key (`GATEWAY_AUTH_ENABLED=false`, stdio) are not recorded.

Call count per tool, per server:

```sql
SELECT s."server_name", t."tool_name", COUNT(c."id") AS "calls"
FROM "tools_mgs" t
JOIN "mcp_app_mgs" s ON s."id" = t."mcp_id"
LEFT JOIN "tool_calls_mgs" c ON c."tool_id" = t."id"
GROUP BY s."server_name", t."tool_name";
```

## Connecting AI clients

**Claude Code**
```bash
claude mcp add --transport http gateway https://gateway.example.com/mcp \
  --header "Authorization: Bearer $GATEWAY_KEY"
```

**Claude Desktop / Cursor / VS Code** (`mcp.json` / `claude_desktop_config.json` style)
```json
{
  "mcpServers": {
    "gateway": {
      "type": "http",
      "url": "https://gateway.example.com/mcp",
      "headers": { "Authorization": "Bearer <your key>" }
    }
  }
}
```

**Local stdio** (no network auth; the client launches the gateway itself)
```json
{ "command": "python", "args": ["/path/to/mcp-gateway-server/mcp_gateway/main.py", "--transport", "stdio"] }
```

**Python**
```python
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

http = create_mcp_http_client(headers={"Authorization": "Bearer <key>"})
async with Client(streamable_http_client("http://localhost:8080/mcp/gateway", http_client=http)) as c:
    print(await c.call_tool("math__add", {"a": 1, "b": 2}))
```

## Production notes

- Put the gateway behind TLS (a reverse proxy or load balancer). API keys are bearer secrets.
- Set `GATEWAY_ALLOWED_HOSTS` to the public hostname(s) to turn on DNS-rebinding protection.
- MCP sessions are held in memory. If you run several replicas, use sticky sessions
  (keyed on the `Mcp-Session-Id` header).

## Layout

```
mcp_gateway/     the gateway (deployable on its own; settings in mcp_gateway/.env)
  main.py               starts the gateway (http | stdio)
  config/settings.py    reads settings from environment variables, validation
  db/                   loads the live servers and API keys from HANA; db/usage.py writes tool usage
  usage/recorder.py     collects tool lists and calls in memory, writes them to HANA in the background
  upstream/pool.py      upstream connections: supervisor, reconnect, catalog cache
  server/gateway.py     MCP handlers: aggregate lists, route calls/reads/prompts
  auth/api_keys.py      API-key ASGI middleware + per-key upstream scoping
  web/app.py            Starlette app: MCP endpoint + /health
servers/
  server_1/ server_2/ server_3/   sample MCP servers (ports 9001-9003)
clients/
  client_1/                 plain MCP client using the admin key
  client_2/ client_3/       GPT-4.1 agents (SAP Gen AI Hub) using server / group keys
backend/        FastAPI admin/user API on SAP HANA (settings in backend/.env)
```
