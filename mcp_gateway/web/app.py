"""HTTP application: Streamable HTTP MCP endpoint + /health, behind API-key auth."""

from __future__ import annotations

from typing import Any

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from mcp_gateway.auth.api_keys import ApiKeyMiddleware
from mcp_gateway.config.settings import GatewayConfig
from mcp_gateway.server.gateway import Gateway, build_server


def create_app(config: GatewayConfig) -> ASGIApp:
    gateway = Gateway(config)
    server = build_server(gateway)
    settings = config.gateway

    async def health(_: Request) -> JSONResponse:
        # Public (no API key), so only names and counts: no server URLs (they can be internal hosts), no error
        # texts, and no client sessions (they name users and their keys). Logs have the details.
        public = ("name", "connected", "tools", "resources", "prompts")
        upstreams = [{k: u[k] for k in public} for u in gateway.pool.status()]
        healthy = any(u["connected"] for u in upstreams) or not upstreams
        return JSONResponse(
            {"status": "ok" if healthy else "degraded", "upstreams": upstreams},
            status_code=200 if healthy else 503,
        )

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
        custom_starlette_routes=[Route("/health", health, methods=["GET"])],
    )
    return ApiKeyMiddleware(app, config.auth, gateway.keys)
