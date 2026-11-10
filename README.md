# mcp-gateway-server

A single MCP endpoint for all AI clients. The gateway connects to every live MCP
server listed in your `.env` file and exposes their tools, resources and prompts
through one authenticated URL. Clients don't connect to upstream servers directly.

```
 Claude / Cursor / VS Code / custom agents
                 │  Authorization: Bearer <api key>
                 ▼
        ┌──────────────────┐
        │   MCP Gateway    │  /mcp     Streamable HTTP endpoint
        │                  │  /health  upstream status (no auth)
        └──────────────────┘
          │       │       │   Streamable HTTP or SSE, with per-upstream headers
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
- **Tool filtering.** Each upstream has `_INCLUDE_TOOLS` / `_EXCLUDE_TOOLS` globs, so you
  can hide dangerous tools (for example `delete_*`).
- **Resilience.** Each upstream has its own supervisor that health-checks the connection
  every 30s and reconnects with exponential backoff. If one upstream is down, the
  others keep working, and calls to the down server get a clear error.
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

cp .env.example .env     # then edit servers + keys
python main.py           # reads .env; use --env-file <path> for another file
```

To try it locally, run the three sample servers (registered as `SERVER_<N>_URL` in `.env`), then the gateway, then a client:

```bash
python servers/server_1/server_1.py    # port 9001
python servers/server_2/server_2.py    # port 9002
python servers/server_3/server_3.py    # port 9003
python main.py                         # gateway on port 8080
python clients/client_1/client.py      # admin key: lists and calls tools on every server
python clients/client_2/client.py      # GPT-4.1 agent with API_KEY_GROUP_4 (server_4 only)
python clients/client_3/client.py      # GPT-4.1 agent with API_KEY_GROUP_1 (server_1 only)
```

## Configuration

All settings are environment variables. The gateway loads them from `.env` (git-ignored);
variables already set in the real environment take precedence. See
[.env.example](.env.example) for a full example.

**Gateway:** `GATEWAY_HOST` (default `0.0.0.0`), `GATEWAY_PORT` (`8080`), `GATEWAY_PATH` (`/mcp`),
`GATEWAY_ALLOWED_HOSTS`, `GATEWAY_LOG_LEVEL` (`INFO`), `GATEWAY_AUTH_ENABLED` (`true`),
`GATEWAY_RECONNECT_INITIAL_DELAY` (`1`), `GATEWAY_RECONNECT_MAX_DELAY` (`60`).

**Client API keys:**

| variable | meaning |
|---|---|
| `API_KEY_<NAME>` | A key clients send as `Authorization: Bearer <key>`; without `_SERVERS` it reaches every server (admin) |
| `API_KEY_<NAME>_SERVERS` | Makes the key a group: comma-separated servers (or globs) it may reach, one or many |

**MCP servers.** `SERVER_<ID>` in lowercase becomes the server's name and tool prefix, so
`SERVER_1_URL` gives tools named `server_1__...`.

| variable | default | meaning |
|---|---|---|
| `SERVER_<ID>_URL` | required | The server's live MCP URL |
| `SERVER_<ID>_TRANSPORT` | `streamable_http` | `streamable_http` or `sse` (legacy servers) |
| `SERVER_<ID>_HEADER_<HEADER>` | | Header sent to the server; `_` becomes `-` (`X_API_KEY` → `X-API-KEY`) |
| `SERVER_<ID>_TIMEOUT` | `60` | Per-request timeout in seconds |
| `SERVER_<ID>_ENABLED` | `true` | Set to `false` to turn off without deleting |
| `SERVER_<ID>_INCLUDE_TOOLS` | all | Comma-separated globs of tools to expose |
| `SERVER_<ID>_EXCLUDE_TOOLS` | none | Comma-separated globs of tools to hide |

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
{ "command": "python", "args": ["/path/to/mcp-gateway-server/main.py", "--transport", "stdio"] }
```

**Python**
```python
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

http = create_mcp_http_client(headers={"Authorization": "Bearer <key>"})
async with Client(streamable_http_client("http://localhost:8080/mcp", http_client=http)) as c:
    print(await c.call_tool("math__add", {"a": 1, "b": 2}))
```

## Production notes

- Put the gateway behind TLS (a reverse proxy or load balancer). API keys are bearer secrets.
- Set `GATEWAY_ALLOWED_HOSTS` to the public hostname(s) to turn on DNS-rebinding protection.
- MCP sessions are held in memory. If you run several replicas, use sticky sessions
  (keyed on the `Mcp-Session-Id` header).
- Generate keys with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Layout

```
main.py         starts the gateway (http | stdio)
gateway/
  config.py     reads settings from environment variables, validation
  upstream.py   upstream connections: supervisor, reconnect, catalog cache
  server.py     MCP handlers: aggregate lists, route calls/reads/prompts
  auth.py       API-key ASGI middleware + per-key upstream scoping
  app.py        Starlette app: /mcp + /health
servers/
  server_1/ server_2/ server_3/   sample MCP servers (ports 9001-9003)
clients/
  client_1/                 plain MCP client using the admin key
  client_2/ client_3/       GPT-4.1 agents (SAP Gen AI Hub) using server / group keys
```
