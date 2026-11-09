"""Connections to upstream (live) MCP servers.

Each upstream is owned by a supervisor task that connects, keeps the session
alive with periodic catalog refreshes, and reconnects with exponential backoff when
the upstream goes away. That shared session is the gateway's own: it lists the catalog.

Client requests (tools/call, resources/read, ...) use a separate session per client key,
opened on first use and sent with `X-MCP-Client: <key name>`, so the server sees which
client is calling and no state is shared between clients. Idle client sessions close
after CLIENT_SESSION_IDLE seconds; all of them close when the shared session drops.

Catalog freshness: the shared session also opens a `subscriptions/listen` stream, so a
server that announces a change gets re-listed within CHANGE_DEBOUNCE seconds. Servers
that can't stream changes are still re-listed every HEALTH_CHECK_INTERVAL seconds. Every
refresh compares the new catalog with the old one and reports what changed to `on_change`,
which the gateway passes on to its own clients.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

import anyio
import mcp_types as types
from mcp.client import Client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.subscriptions import ListenNotSupportedError, SubscriptionLost
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError
from mcp.shared.subscriptions import PromptsListChanged, ResourcesListChanged, ServerEvent, ToolsListChanged

from gateway.config import GatewaySettings, UpstreamConfig

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 30.0
CATALOG_TTL = 30.0
CHANGE_DEBOUNCE = 1.0  # a burst of change events from one server becomes one refresh
CLIENT_SESSION_IDLE = 300.0
CLIENT_ID_HEADER = "X-MCP-Client"

# Called with (server name, what changed) whenever a server's catalog changes.
OnChange = Callable[[str, list[ServerEvent]], None]


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

    def changes_from(self, old: Catalog) -> list[ServerEvent]:
        """Which lists differ from `old`, as the events clients listen for."""
        changes: list[ServerEvent] = []
        if self.tools != old.tools:
            changes.append(ToolsListChanged())
        if (self.resources, self.resource_templates) != (old.resources, old.resource_templates):
            changes.append(ResourcesListChanged())
        if self.prompts != old.prompts:
            changes.append(PromptsListChanged())
        return changes


@dataclass
class ClientSession:
    """One client key's own session to an upstream."""

    ready: anyio.Event = field(default_factory=anyio.Event)
    closed: anyio.Event = field(default_factory=anyio.Event)
    client: Client | None = None
    error: str | None = None
    last_used: float = field(default_factory=time.monotonic)


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
    def __init__(self, config: UpstreamConfig, settings: GatewaySettings, on_change: OnChange | None = None) -> None:
        self.config = config
        self.settings = settings
        self.client: Client | None = None
        self.catalog = Catalog()
        self.last_error: str | None = None
        self._on_change = on_change
        self._broken = anyio.Event()
        self._changed = anyio.Event()
        self._refresh_lock = anyio.Lock()
        self._sessions: dict[str, ClientSession] = {}
        self._session_tg: anyio.abc.TaskGroup | None = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def connected(self) -> bool:
        return self.client is not None

    def _transport(self, stack: AsyncExitStack, caller: str | None = None) -> Any:
        cfg = self.config
        headers = {**cfg.headers, CLIENT_ID_HEADER: caller} if caller else cfg.headers
        if cfg.transport == "sse":
            return sse_client(cfg.url, headers=headers or None, timeout=cfg.timeout_seconds)
        http_client = create_mcp_http_client(headers=headers or None)
        stack.push_async_callback(http_client.aclose)
        return streamable_http_client(cfg.url, http_client=http_client)

    def _new_client(self, stack: AsyncExitStack, caller: str | None = None) -> Client:
        return Client(
            self._transport(stack, caller),
            read_timeout_seconds=self.config.timeout_seconds,
            client_info=types.Implementation(name=self.settings.name, version="1.0.0"),
            cache=None,
        )

    async def run(self) -> None:
        """Supervisor loop: connect, serve, reconnect forever (until cancelled)."""
        delay = self.settings.reconnect_initial_delay
        while True:
            try:
                async with AsyncExitStack() as stack:
                    client = self._new_client(stack)
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
                    async with anyio.create_task_group() as tg:  # hosts the per-client sessions and change listener
                        self._session_tg = tg
                        self._changed = anyio.Event()
                        tg.start_soon(self._listen, client)
                        tg.start_soon(self._apply_changes)
                        await self._monitor()
                        tg.cancel_scope.cancel()
            except anyio.get_cancelled_exc_class():
                raise
            except BaseException as exc:  # noqa: BLE001 - transports raise ExceptionGroups
                self.last_error = _describe(exc)
                logger.warning("Upstream '%s' unavailable: %s", self.name, self.last_error)
            finally:
                self.client = None
                self._session_tg = None
                self._broken = anyio.Event()
                self._set_catalog(Catalog())  # its items are gone from every list until it reconnects

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

    async def _listen(self, client: Client) -> None:
        """Flag a refresh whenever the server reports a change, instead of waiting for the next poll."""
        try:
            async with client.listen(
                tools_list_changed=True, prompts_list_changed=True, resources_list_changed=True
            ) as subscription:
                logger.info("Listening for changes from '%s'", self.name)
                async for _ in subscription:
                    self._changed.set()
            logger.info("'%s' closed its change stream; polling every %.0fs", self.name, HEALTH_CHECK_INTERVAL)
        except (ListenNotSupportedError, MCPError) as exc:
            logger.info("'%s' can't stream changes (%s); polling every %.0fs", self.name, exc, HEALTH_CHECK_INTERVAL)
        except SubscriptionLost as exc:
            logger.warning("Change stream from '%s' dropped: %s", self.name, exc)
            self.mark_broken()  # reconnecting re-opens the stream

    async def _apply_changes(self) -> None:
        """Re-list once per burst of change events."""
        while True:
            await self._changed.wait()
            await anyio.sleep(CHANGE_DEBOUNCE)  # events arriving meanwhile are folded into this refresh
            self._changed = anyio.Event()
            try:
                with anyio.fail_after(self.config.timeout_seconds):
                    await self.refresh_catalog(force=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Refresh of '%s' after a change failed: %s", self.name, exc)
                self.mark_broken()

    def mark_broken(self) -> None:
        self._broken.set()

    async def client_for(self, caller: str | None) -> Client:
        """The session to use for `caller` (a client key name); None means the gateway's shared session."""
        shared = self.require_client()
        if caller is None or self._session_tg is None:
            return shared
        session = self._sessions.get(caller)
        if session is None or session.closed.is_set():
            session = self._sessions[caller] = ClientSession()
            self._session_tg.start_soon(self._serve_client, caller, session)
        with anyio.move_on_after(self.config.timeout_seconds):
            await session.ready.wait()
        if session.client is None:
            raise UpstreamUnavailableError(
                f"Upstream '{self.name}' refused a session for '{caller}': {session.error or 'timed out'}"
            )
        session.last_used = time.monotonic()
        return session.client

    def close_client(self, caller: str | None) -> None:
        if caller is not None and (session := self._sessions.get(caller)):
            session.closed.set()

    async def _serve_client(self, caller: str, session: ClientSession) -> None:
        """Owns one client's session: open it, keep it until idle or closed, then close it."""
        try:
            async with AsyncExitStack() as stack:
                client = self._new_client(stack, caller)
                await stack.enter_async_context(client)
                session.client = client
                session.ready.set()
                logger.info("Opened session to '%s' for client '%s'", self.name, caller)
                while (idle := time.monotonic() - session.last_used) < CLIENT_SESSION_IDLE:
                    with anyio.move_on_after(CLIENT_SESSION_IDLE - idle):
                        await session.closed.wait()
                        break
                logger.info("Closed session to '%s' for client '%s'", self.name, caller)
        except anyio.get_cancelled_exc_class():
            raise
        except BaseException as exc:  # noqa: BLE001 - transports raise ExceptionGroups
            session.error = _describe(exc)
            logger.warning("Session to '%s' for client '%s' failed: %s", self.name, caller, session.error)
        finally:
            session.client = None
            session.closed.set()
            session.ready.set()
            if self._sessions.get(caller) is session:
                del self._sessions[caller]

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
            self._set_catalog(catalog)

    def _set_catalog(self, catalog: Catalog) -> None:
        changes = catalog.changes_from(self.catalog)
        self.catalog = catalog
        if changes and self._on_change is not None:
            logger.info("'%s' changed: %s", self.name, ", ".join(type(c).__name__ for c in changes))
            self._on_change(self.name, changes)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.config.url,
            "transport": self.config.transport,
            "connected": self.connected,
            "tools": len(self.catalog.tools) if self.connected else 0,
            "resources": len(self.catalog.resources) if self.connected else 0,
            "prompts": len(self.catalog.prompts) if self.connected else 0,
            "client_sessions": sorted(self._sessions),
            "last_error": self.last_error,
        }


def _describe(exc: BaseException) -> str:
    """Flatten ExceptionGroups into a readable message."""
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe(e) for e in exc.exceptions)
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


class UpstreamPool:
    def __init__(
        self, configs: list[UpstreamConfig], settings: GatewaySettings, on_change: OnChange | None = None
    ) -> None:
        self.upstreams: dict[str, Upstream] = {c.name: Upstream(c, settings, on_change) for c in configs}

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
