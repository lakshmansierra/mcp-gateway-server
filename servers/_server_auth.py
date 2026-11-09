"""Bearer-token check for the sample MCP servers: only callers holding the server's token (the gateway) get in.

Each server reads its token from SERVER_<ID>_HEADER_AUTHORIZATION in the project's .env (e.g.
SERVER_1_HEADER_AUTHORIZATION for server_1): the same line the gateway uses to send it, as
"Authorization: Bearer <token>".

The gateway also sends `X-MCP-Client: <key name>` naming the client it is calling for. Only the
gateway holds the token, so behind this check that header can be trusted; `client_of(ctx)` reads it.
"""

from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import Context
from starlette.types import ASGIApp, Receive, Scope, Send

CLIENT_ID_HEADER = "x-mcp-client"


def client_of(ctx: Context) -> str:
    """The client the gateway is calling for, or 'unknown' (direct callers, auth-off gateways)."""
    return (ctx.headers or {}).get(CLIENT_ID_HEADER, "unknown")


def token_for(server_name: str) -> str | None:
    """The token this server expects, from <NAME>_HEADER_AUTHORIZATION in the nearest .env above this file."""
    env_file = next((f / ".env" for f in Path(__file__).resolve().parents if (f / ".env").is_file()), None)
    load_dotenv(env_file)
    value = os.environ.get(f"{server_name.upper()}_HEADER_AUTHORIZATION", "").strip()
    return value.removeprefix("Bearer ").strip() or None


class RequireBearerToken:
    """ASGI middleware: rejects HTTP requests whose `Authorization: Bearer <token>` doesn't match."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            presented = dict(scope.get("headers", [])).get(b"authorization", b"")
            if not hmac.compare_digest(presented, self.expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body",
                            "body": json.dumps({"error": "unauthorized"}).encode()})
                return
        await self.app(scope, receive, send)


def protect(app: ASGIApp, server_name: str, token: str | None = None) -> ASGIApp:
    """Wrap a server's app with the token check, or leave it open (with a notice) when no token is configured."""
    token = token or token_for(server_name)
    if not token:
        print(f"[{server_name}] no {server_name.upper()}_HEADER_AUTHORIZATION set: accepting requests without a token")
        return app
    print(f"[{server_name}] requiring 'Authorization: Bearer <token>' on every request")
    return RequireBearerToken(app, token)
