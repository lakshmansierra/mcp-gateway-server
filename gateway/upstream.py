"""Connections to upstream (live) MCP servers.

Each upstream is owned by a supervisor task that connects, keeps the session
alive with periodic pings, and reconnects with exponential backoff when the
upstream goes away. Request handlers only borrow the live `Client`.
"""

from __future__ import annotations

import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import anyio
import mcp_types as types
from mcp.client import Client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from gateway.config import GatewaySettings, UpstreamConfig

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 30.0
CATALOG_TTL = 30.0


class UpstreamUnavailableError(RuntimeError):
    pass


@dataclass
class Catalog:
    """Everything an upstream exposes, as last fetched."""

    tools: list[types.Tool] = field(default_factory=list)
    resources: list[types.Resource] = field(default_factory=list)
    resource_templates: list[types.ResourceTemplate] = field(default_factory=list)
    prompts: list[types.Prompt] = field(default_factory=list)
    fetched_at: float = 0.0


async def _collect(fetch: Any, attr: str) -> list[Any]:
    """Drain a paginated list endpoint."""
    items: list[Any] = []
    cursor: str | None = None
    while True:
        page = await fetch(cursor=cursor)
        items.extend(getattr(page, attr))
        cursor = page.next_cursor
        if not cursor:
            return items


class Upstream:
    def __init__(self, config: UpstreamConfig, settings: GatewaySettings) -> None:
        self.config = config
        self.settings = settings
        self.client: Client | None = None
        self.catalog = Catalog()
        self.last_error: str | None = None
        self._broken = anyio.Event()
        self._refresh_lock = anyio.Lock()

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def connected(self) -> bool:
        return self.client is not None

    def _transport(self, stack: AsyncExitStack) -> Any:
        cfg = self.config
        if cfg.transport == "sse":
            return sse_client(cfg.url, headers=cfg.headers or None, timeout=cfg.timeout_seconds)
        http_client = create_mcp_http_client(headers=cfg.headers or None)
        stack.push_async_callback(http_client.aclose)
        return streamable_http_client(cfg.url, http_client=http_client)

    async def run(self) -> None:
        """Supervisor loop: connect, serve, reconnect forever (until cancelled)."""
        delay = self.settings.reconnect_initial_delay
        while True:
            try:
                async with AsyncExitStack() as stack:
                    client = Client(
                        self._transport(stack),
                        read_timeout_seconds=self.config.timeout_seconds,
                        client_info=types.Implementation(name=self.settings.name, version="1.0.0"),
                        cache=None,
                    )
                    await stack.enter_async_context(client)
                    self.client = client
                    await self.refresh_catalog(force=True)
                    self.last_error = None
                    delay = self.settings.reconnect_initial_delay
                    logger.info(
                        "Upstream '%s' connected (%d tools, %d resources, %d prompts)",
                        self.name,
                        len(self.catalog.tools),
                        len(self.catalog.resources),
                        len(self.catalog.prompts),
                    )
                    await self._monitor()
            except anyio.get_cancelled_exc_class():
                raise
            except BaseException as exc:  # noqa: BLE001 - transports raise ExceptionGroups
                self.last_error = _describe(exc)
                logger.warning("Upstream '%s' unavailable: %s", self.name, self.last_error)
            finally:
                self.client = None
                self._broken = anyio.Event()

            logger.info("Reconnecting to '%s' in %.1fs", self.name, delay)
            await anyio.sleep(delay)
            delay = min(delay * 2, self.settings.reconnect_max_delay)

    async def _monitor(self) -> None:
        """Return when the connection should be torn down."""
        while True:
            with anyio.move_on_after(HEALTH_CHECK_INTERVAL):
                await self._broken.wait()
                self.last_error = "connection reported broken by a request"
                return
            # Re-listing doubles as a liveness probe (ping is gone in 2026-07-28) and keeps the catalog fresh.
            with anyio.fail_after(self.config.timeout_seconds):
                await self.refresh_catalog(force=True)

    def mark_broken(self) -> None:
        self._broken.set()

    def require_client(self) -> Client:
        if self.client is None:
            raise UpstreamUnavailableError(
                f"Upstream '{self.name}' is not connected" + (f": {self.last_error}" if self.last_error else "")
            )
        return self.client

    async def refresh_catalog(self, force: bool = False) -> None:
        if not force and time.monotonic() - self.catalog.fetched_at < CATALOG_TTL:
            return
        async with self._refresh_lock:
            if not force and time.monotonic() - self.catalog.fetched_at < CATALOG_TTL:
                return
            client = self.require_client()
            caps = client.server_capabilities
            catalog = Catalog(fetched_at=time.monotonic())
            if caps.tools is not None:
                tools = await _collect(client.list_tools, "tools")
                catalog.tools = [t for t in tools if self.config.tool_allowed(t.name)]
            if caps.resources is not None:
                catalog.resources = await _collect(client.list_resources, "resources")
                catalog.resource_templates = await _collect(client.list_resource_templates, "resource_templates")
            if caps.prompts is not None:
                catalog.prompts = await _collect(client.list_prompts, "prompts")
            self.catalog = catalog

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.config.url,
            "transport": self.config.transport,
            "connected": self.connected,
            "tools": len(self.catalog.tools) if self.connected else 0,
            "resources": len(self.catalog.resources) if self.connected else 0,
            "prompts": len(self.catalog.prompts) if self.connected else 0,
            "last_error": self.last_error,
        }


def _describe(exc: BaseException) -> str:
    """Flatten ExceptionGroups into a readable message."""
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe(e) for e in exc.exceptions)
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class UpstreamPool:
    def __init__(self, configs: list[UpstreamConfig], settings: GatewaySettings) -> None:
        self.upstreams: dict[str, Upstream] = {c.name: Upstream(c, settings) for c in configs}

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            for upstream in self.upstreams.values():
                tg.start_soon(upstream.run, name=f"upstream:{upstream.name}")

    async def wait_until_ready(self, timeout: float) -> None:
        """Give upstreams a moment to connect at startup so the first tools/list is complete."""
        with anyio.move_on_after(timeout):
            while not all(u.connected or u.last_error for u in self.upstreams.values()):
                await anyio.sleep(0.1)

    def get(self, name: str) -> Upstream | None:
        return self.upstreams.get(name)

    def status(self) -> list[dict[str, Any]]:
        return [u.status() for u in self.upstreams.values()]
