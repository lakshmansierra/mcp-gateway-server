"""OAuth2 access tokens for upstream MCP servers.

The gateway obtains a short-lived access token from an upstream's token endpoint (client_credentials or password
grant), caches it in memory and in HANA (token cache table) with its expiry, and refetches when it expires or the
upstream rejects it. Only OAuth2 servers use this; bearer/basic send a static header built from stored secrets.

Headless note: only client_credentials and password grants work without a browser, so those are the only two the
gateway supports. The authorization_code and implicit grants need an interactive login and aren't handled here.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import anyio
import httpx

from mcp_gateway.config.settings import AuthConfig, DatabaseSettings
from mcp_gateway.db import token_cache
from mcp_gateway.db.connection import connect

logger = logging.getLogger(__name__)

_EXPIRY_MARGIN = 60.0  # refresh this many seconds before the token actually expires, so it never expires mid-request
_DEFAULT_TTL = 3600.0  # assumed lifetime when the token endpoint doesn't send expires_in


class OAuthError(RuntimeError):
    """The token endpoint couldn't be reached or didn't return a usable access token."""


class TokenStore:
    """Fetches and caches OAuth2 access tokens, one per server (by its row id). Shared across the upstream pool."""

    def __init__(self, db: DatabaseSettings) -> None:
        self.db = db
        self._cache: dict[int, tuple[str, float]] = {}  # mcp_id -> (access_token, expires_at as epoch seconds)
        self._locks: dict[int, anyio.Lock] = {}

    def _lock(self, mcp_id: int) -> anyio.Lock:
        lock = self._locks.get(mcp_id)
        if lock is None:
            lock = self._locks[mcp_id] = anyio.Lock()
        return lock

    async def token(self, auth: AuthConfig, mcp_id: int, timeout: float, *, force: bool = False) -> str:
        """A valid access token for the server: the cached one if it's still fresh, otherwise a freshly fetched
        one (also written to the cache). force=True skips the cache (used after the upstream rejects a token).
        Raises OAuthError if a token can't be obtained."""
        async with self._lock(mcp_id):
            now = time.time()
            if not force:
                cached = self._cache.get(mcp_id)
                if cached and cached[1] - _EXPIRY_MARGIN > now:
                    return cached[0]
                from_db = await self._read_db(mcp_id)
                if from_db and from_db[1] - _EXPIRY_MARGIN > now:
                    self._cache[mcp_id] = from_db
                    return from_db[0]
            token, expires_at = await self._fetch(auth, timeout)
            self._cache[mcp_id] = (token, expires_at)
            await self._write_db(mcp_id, token, expires_at)
            logger.info("Fetched a new OAuth2 access token for server %s (valid ~%.0fs)", mcp_id, expires_at - now)
            return token

    async def _fetch(self, auth: AuthConfig, timeout: float) -> tuple[str, float]:
        if not auth.token_url:
            raise OAuthError("no token_url configured")
        grant = auth.oauth_grant_type or "client_credentials"
        data: dict[str, str] = {"grant_type": grant}
        if auth.scope:
            data["scope"] = auth.scope
        if grant == "password":
            data["username"] = auth.username or ""
            data["password"] = auth.password or ""
        basic: httpx.BasicAuth | None = None
        if (auth.client_authentication or "basic_header") == "basic_header":
            basic = httpx.BasicAuth(auth.client_id or "", auth.client_secret or "")
        else:  # send client credentials in the body
            data["client_id"] = auth.client_id or ""
            data["client_secret"] = auth.client_secret or ""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(auth.token_url, data=data, auth=basic, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise OAuthError(f"could not reach the token endpoint: {exc}") from exc
        if resp.status_code >= 400:
            raise OAuthError(f"token endpoint returned {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise OAuthError(f"token endpoint returned non-JSON: {resp.text[:200]}") from exc
        access = body.get("access_token")
        if not access:
            raise OAuthError("token endpoint returned no access_token")
        expires_in = body.get("expires_in")
        ttl = float(expires_in) if expires_in else _DEFAULT_TTL
        return access, time.time() + ttl

    async def _read_db(self, mcp_id: int) -> tuple[str, float] | None:
        def job() -> tuple[str | None, datetime | None] | None:
            conn = connect(self.db)
            try:
                cur = conn.cursor()
                try:
                    return token_cache.read(cur, self.db, mcp_id)
                finally:
                    cur.close()
            finally:
                conn.close()

        try:
            row = await anyio.to_thread.run_sync(job, abandon_on_cancel=True)
        except Exception as exc:  # noqa: BLE001 - cache is best-effort; fall through to a fresh fetch
            logger.warning("Could not read the OAuth2 token cache for server %s: %s", mcp_id, exc)
            return None
        if row is None or row[0] is None or row[1] is None:
            return None
        token, expires_dt = row
        epoch = expires_dt.replace(tzinfo=timezone.utc).timestamp()
        return token, epoch

    async def _write_db(self, mcp_id: int, token: str, expires_at: float) -> None:
        expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc).replace(tzinfo=None)

        def job() -> None:
            conn = connect(self.db)
            try:
                cur = conn.cursor()
                try:
                    token_cache.write(cur, self.db, mcp_id, token, expires_dt)
                    conn.commit()
                finally:
                    cur.close()
            finally:
                conn.close()

        try:
            await anyio.to_thread.run_sync(job, abandon_on_cancel=True)
        except Exception as exc:  # noqa: BLE001 - cache is best-effort; the in-memory copy still works
            logger.warning("Could not write the OAuth2 token cache for server %s: %s", mcp_id, exc)
