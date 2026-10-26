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
- **Tool filtering.** Each upstream has `_INCLUDE_TOOLS` / `_EXCLUDE_TOOLS` globs, so you
  can hide dangerous tools (for example `delete_*`).
- **Resilience.** Each upstream has its own supervisor that health-checks the connection
  every 30s and reconnects with exponential backoff. If one upstream is down, the
  others keep working, and calls to the down server get a clear error.
- **Configured by environment variables.** Settings come from a `.env` file or the real environment.
- **Transports.** HTTP for remote clients; stdio for local clients that launch the gateway as a subprocess.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt

cp .env.example .env     # then edit servers + keys
python main.py           # reads .env; use --env-file <path> for another file
```

To try it locally, run the two sample servers (registered as `SERVER_1_URL` / `SERVER_2_URL` in `.env`):

```bash
python examples/server_1.py      # port 9001
python examples/server_2.py      # port 9002
python main.py                   # gateway on port 8080
python examples/client.py        # lists and calls the tools through the gateway
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
| `API_KEY_<NAME>` | A key clients send as `Authorization: Bearer <key>` |
| `API_KEY_<NAME>_SERVERS` | Optional comma-separated globs; the key only sees those servers |

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
examples/server_1.py   a small MCP server for local testing (port 9001)
examples/server_2.py   a second copy on port 9002
examples/client.py     a client that calls the tools through the gateway
```
