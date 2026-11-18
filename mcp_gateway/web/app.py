"""HTTP application: Streamable HTTP MCP endpoint, behind API-key auth, plus two routes without an API key:
the health route (GATEWAY_HEALTH_PATH) and the reload route (GATEWAY_RELOAD_PATH) the backend calls after a
change, which needs GATEWAY_RELOAD_SECRET instead."""

from __future__ import annotations

import hmac
import logging
from typing import Any

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from mcp_gateway.auth.api_keys import ApiKeyMiddleware
from mcp_gateway.config.settings import GatewayConfig
from mcp_gateway.server.gateway import Gateway, build_server

logger = logging.getLogger(__name__)


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else None


def create_app(config: GatewayConfig) -> ASGIApp:
    gateway = Gateway(config)
    server = build_server(gateway)
    settings = config.gateway

    async def health(_: Request) -> JSONResponse:
        # Public (no API key), so only names and counts: no server URLs (they can be internal hosts), no error
        # texts, and no client sessions (they name users and their keys). Logs have the details.
        public = ("name", "enabled", "connected", "tools", "resources", "prompts")
        upstreams = [{k: u[k] for k in public} for u in gateway.pool.status()]
        healthy = any(u["connected"] for u in upstreams) or not upstreams
        return JSONResponse(
            {"status": "ok" if healthy else "degraded", "upstreams": upstreams},
            status_code=200 if healthy else 503,
        )

    async def reload(request: Request) -> JSONResponse:
        """The backend changed a server, key or user: re-read HANA now and answer once it is applied."""
        secret = settings.reload_secret
        if not secret:
            return JSONResponse(
                {"error": "disabled", "message": "Set GATEWAY_RELOAD_SECRET to turn on reloads"}, status_code=404
            )
        presented = _bearer(request)
        if presented is None or not hmac.compare_digest(presented.encode(), secret.encode()):
            client = request.client
            logger.warning("Rejected reload request from %s: wrong or missing secret", client.host if client else "?")
            return JSONResponse({"error": "unauthorized", "message": "Wrong or missing reload secret"}, status_code=401)
        # Long enough for one full read of HANA (connect + queries), plus a little for applying it.
        wait = config.database.connect_timeout + config.database.query_timeout + 5
        done = await gateway.request_reload(wait)
        if done is None:
            return JSONResponse({"status": "pending", "message": "Still re-reading HANA; it applies when done"}, status_code=504)
        if not done.ok:
            return JSONResponse(
                {"status": "failed", "message": "Could not re-read HANA; the current servers and keys stay in use"},
                status_code=503,
            )
        return JSONResponse({"status": "reloaded", "servers": len(gateway.pool.upstreams), "api_keys": len(gateway.keys)})

    security: Any = None
    if settings.allowed_hosts:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=[f"{scheme}://{h}" for h in settings.allowed_hosts for scheme in ("http", "https")],
        )
    elif settings.host not in ("127.0.0.1", "localhost", "::1"):
        # Exposed on the network: access is controlled by API keys instead of Host checks.
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    app = server.streamable_http_app(
        streamable_http_path=settings.path,
        host=settings.host,
        transport_security=security,
        custom_starlette_routes=[
            Route(settings.health_path, health, methods=["GET"]),
            Route(settings.reload_path, reload, methods=["POST"]),
        ],
    )
    return ApiKeyMiddleware(app, config.auth, gateway.keys, public_paths={settings.health_path, settings.reload_path})
