"""API-key authentication for AI clients connecting to the gateway."""

from __future__ import annotations

import hmac
import json
import logging
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from gateway.config import ApiKeyConfig, AuthSettings

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {"/health"}
SCOPE_KEY = "gateway_api_key"


def _extract_key(scope: Scope) -> str | None:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-api-key")


class ApiKeyMiddleware:
    """Rejects requests without a valid key; stores the matched key on the ASGI scope state."""

    def __init__(self, app: ASGIApp, settings: AuthSettings) -> None:
        self.app = app
        self.settings = settings

    def _match(self, presented: str | None) -> ApiKeyConfig | None:
        if not presented:
            return None
        for cfg in self.settings.api_keys:
            if hmac.compare_digest(cfg.key.encode(), presented.encode()):
                return cfg
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.enabled or scope["path"] in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        key = self._match(_extract_key(scope))
        if key is None:
            client = scope.get("client")
            logger.warning("Rejected unauthenticated request from %s to %s", client[0] if client else "?", scope["path"])
            await _unauthorized(send)
            return

        scope.setdefault("state", {})[SCOPE_KEY] = key
        await self.app(scope, receive, send)


async def _unauthorized(send: Send) -> None:
    body = json.dumps({"error": "unauthorized", "message": "Provide a valid API key via 'Authorization: Bearer <key>'"})
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="mcp-gateway"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body.encode()})


def api_key_from_request(request: Any) -> ApiKeyConfig | None:
    """The key that authenticated this request, or None (stdio / auth disabled)."""
    if request is None:
        return None
    state = getattr(request, "scope", {}).get("state", {})
    return state.get(SCOPE_KEY)
