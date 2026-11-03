"""Bearer-token check for the sample MCP servers: only callers holding one of the server's tokens get in.

Each server reads its tokens from the project's .env (shown for server_1):
    SERVER_1_HEADER_AUTHORIZATION=<token>                the gateway's own token
    SERVER_1_CLIENT_<KEY>_HEADER_AUTHORIZATION=<token>   client key <KEY>'s own token
The gateway sends these same lines as "Authorization: Bearer <token>".

The gateway also sends `X-MCP-Client: <key name>` naming the client it is calling for. A client's own
token must match that header, so it can't be used for another client. Only the gateway holds the tokens,
so behind this check the header can be trusted; `client_of(ctx)` and `token_owner(ctx)` read them.
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
GATEWAY = "gateway"


def client_of(ctx: Context) -> str:
    """The client the gateway is calling for, or 'unknown' (direct callers, auth-off gateways)."""
    return (ctx.headers or {}).get(CLIENT_ID_HEADER, "unknown")


def token_owner(ctx: Context) -> str:
    """Whose token let this request in: 'gateway', a client key name, or 'none' (no token required)."""
    request = ctx.request_context.request
    return getattr(getattr(request, "state", None), "token_owner", "none")


def tokens_for(server_name: str) -> dict[str, str]:
    """token -> owner for this server, from the nearest .env above this file."""
    env_file = next((f / ".env" for f in Path(__file__).resolve().parents if (f / ".env").is_file()), None)
    load_dotenv(env_file)
    prefix, suffix = f"{server_name.upper()}_", "_HEADER_AUTHORIZATION"
    tokens = {}
    for var, value in os.environ.items():
        if not (var.startswith(prefix) and var.endswith(suffix)):
            continue
        middle = var[len(prefix) : -len(suffix)]  # "" for the gateway's token, "CLIENT_<KEY>" for a client's
        if middle and not middle.startswith("CLIENT_"):
            continue
        token = value.strip().removeprefix("Bearer ").strip()
        if token:
            tokens[token] = middle.removeprefix("CLIENT_").lower() or GATEWAY
    return tokens


class RequireBearerToken:
    """ASGI middleware: rejects HTTP requests without a known `Authorization: Bearer <token>`."""

    def __init__(self, app: ASGIApp, tokens: dict[str, str]) -> None:
        self.app = app
        self.tokens = {f"Bearer {t}".encode(): owner for t, owner in tokens.items()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            presented = headers.get(b"authorization", b"")
            owner = next((o for t, o in self.tokens.items() if hmac.compare_digest(presented, t)), None)
            client = headers.get(CLIENT_ID_HEADER.encode(), b"").decode()
            if owner is None:
                return await _reject(send, "unauthorized")
            if owner != GATEWAY and owner != client:
                return await _reject(send, f"this token belongs to client '{owner}'")
            scope.setdefault("state", {})["token_owner"] = owner
        await self.app(scope, receive, send)


async def _reject(send: Send, error: str) -> None:
    await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": json.dumps({"error": error}).encode()})


def protect(app: ASGIApp, server_name: str, token: str | None = None) -> ASGIApp:
    """Wrap a server's app with the token check, or leave it open (with a notice) when no token is configured."""
    tokens = tokens_for(server_name)
    if token:
        tokens[token] = GATEWAY
    if not tokens:
        print(f"[{server_name}] no {server_name.upper()}_HEADER_AUTHORIZATION set: accepting requests without a token")
        return app
    clients = sorted(o for o in tokens.values() if o != GATEWAY)
    print(f"[{server_name}] requiring 'Authorization: Bearer <token>'; clients with their own token: {clients or 'none'}")
    return RequireBearerToken(app, tokens)
