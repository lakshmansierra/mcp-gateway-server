"""API-key authentication for AI clients connecting to the gateway.

The keys are the live rows of the key table in HANA, which hold only each key's SHA-256 hash. A request's key
is hashed the same way (as the backend does when it creates the key) and looked up by that hash.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_gateway.config.settings import ApiKeyConfig, AuthSettings

logger = logging.getLogger(__name__)

SCOPE_KEY = "gateway_api_key"


def hash_api_key(key: str) -> str:
    """Same as the backend's backend/security.py hash_api_key: what the key table stores."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class KeyStore:
    """The live API keys, replaced as a whole after every read of the key table."""

    def __init__(self, keys: list[ApiKeyConfig] | None = None) -> None:
        self._by_hash: dict[str, ApiKeyConfig] = {}
        self._by_id: dict[int, ApiKeyConfig] = {}
        self.replace(keys or [])

    def replace(self, keys: list[ApiKeyConfig]) -> None:
        old = {k.id: k for k in self._by_hash.values()}
        new = {k.id: k for k in keys}
        self._by_hash, self._by_id = {k.key_hash: k for k in keys}, new
        added = sorted(new[i].name for i in new.keys() - old.keys())
        removed = sorted(old[i].name for i in old.keys() - new.keys())
        changed = sorted(k.name for i, k in new.items() if i in old and old[i] != k)  # rotated or servers changed
        if old and (added or removed or changed):
            logger.info("API keys changed: added %s, removed %s, changed %s", added, removed, changed)

    def get(self, key_id: int) -> ApiKeyConfig | None:
        """The key with this id as of the last read, or None if it was deleted since."""
        return self._by_id.get(key_id)

    def match(self, presented: str | None) -> ApiKeyConfig | None:
        return self._by_hash.get(hash_api_key(presented)) if presented else None

    def __len__(self) -> int:
        return len(self._by_hash)


def _extract_key(scope: Scope) -> str | None:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-api-key")


class ApiKeyMiddleware:
    """Rejects requests without a valid key; stores the matched key on the ASGI scope state."""

    def __init__(self, app: ASGIApp, settings: AuthSettings, keys: KeyStore, public_paths: set[str]) -> None:
        self.app = app
        self.settings = settings
        self.keys = keys
        self.public_paths = public_paths  # answered without a key (GATEWAY_HEALTH_PATH)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.enabled or scope["path"] in self.public_paths:
            await self.app(scope, receive, send)
            return

        key = self.keys.match(_extract_key(scope))
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
