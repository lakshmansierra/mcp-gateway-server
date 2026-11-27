"""Connections to upstream (live) MCP servers.

Each upstream is owned by a supervisor task that connects, keeps the session
alive with periodic catalog refreshes, and reconnects with exponential backoff when
the upstream goes away. That shared session is the gateway's own: it lists the catalog.

Client requests (tools/call, resources/read, ...) use a separate session per client key,
opened on first use and sent with `<GATEWAY_CLIENT_ID_HEADER>: <key name>` (X-MCP-Client by default), so the server sees which
client is calling and no state is shared between clients. Idle client sessions close
after client_session_idle seconds; all of them close when the shared session drops.

Catalog freshness: the shared session also opens a `subscriptions/listen` stream, so a
server that announces a change gets re-listed within change_debounce seconds. Servers
that can't stream changes are still re-listed every health_check_interval seconds. Every
refresh compares the new catalog with the old one and reports what changed to `on_change`,
which the gateway passes on to its own clients. Each successful re-list also reports the server's full tool
list (before include/exclude filtering) to `on_tools`, for the tool usage tables, when it differs from the
last one reported.

The set of servers can change while the gateway runs: `UpstreamPool.apply` starts new servers, stops removed
ones, reconnects servers whose URL, transport or timeout changed, and re-filters the catalog of servers whose
tool filters changed (no reconnect needed). Disabled servers stay connected (their owning admin may still use
them); enabling or disabling one only changes who may see it, and tells listening clients to re-list.
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

from mcp_gateway.config.settings import GatewaySettings, UpstreamConfig
from mcp_gateway.upstream.oauth import TokenStore

logger = logging.getLogger(__name__)

# Called with (server name, what changed) whenever a server's catalog changes.
OnChange = Callable[[str, list[ServerEvent]], None]
# Called with (server row id, server name, its full tool list) after a re-list that found a different list.
OnTools = Callable[[int, str, list[types.Tool]], None]


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
    def __init__(
        self,
        config: UpstreamConfig,
        settings: GatewaySettings,
        on_change: OnChange | None = None,
        on_tools: OnTools | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        self.config = config
        self.settings = settings
        self._token_store = token_store  # shared OAuth2 token cache; None if the gateway has no DB-backed store
        self.client: Client | None = None
        self.catalog = Catalog()
        self.last_error: str | None = None
        self._on_change = on_change
        self._on_tools = on_tools
        self._reported_tools: tuple[int, list[types.Tool]] | None = None  # last (row id, list) sent to on_tools
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

    def _is_oauth(self) -> bool:
        return self.config.auth is not None and self.config.auth.auth_type == "oauth2"

    async def _authorization(self, force: bool = False) -> dict[str, str] | None:
        """The Authorization header to send to this upstream, or None for no auth. Bearer/basic are built from
        stored secrets; oauth2 fetches (or reuses a cached) access token. force=True refetches an oauth2 token
        (used on reconnect after the server rejected the last one). Any failure logs and returns None so the
        connection is still attempted (the upstream then answers 401, surfaced as last_error)."""
        auth = self.config.auth
        if auth is None:
            return None
        if auth.auth_type in ("bearer", "basic"):
            return auth.static_header()
        if auth.auth_type == "oauth2":
            if self._token_store is None or self.config.id is None:
                logger.warning(
                    "Upstream '%s' uses OAuth2 but no token store is available; connecting without a token", self.name
                )
                return None
            try:
                token = await self._token_store.token(auth, self.config.id, self.config.timeout_seconds, force=force)
            except Exception as exc:  # noqa: BLE001 - token endpoint down or misconfigured
                logger.warning(
                    "Could not obtain an OAuth2 token for '%s' (auth may be misconfigured or the token endpoint "
                    "is unreachable): %s",
                    self.name,
                    exc,
                )
                return None
            prefix = (auth.header_prefix or "Bearer").strip()
            return {"Authorization": f"{prefix} {token}".strip()}
        return None

    def _transport(self, stack: AsyncExitStack, caller: str | None = None, auth_header: dict[str, str] | None = None) -> Any:
        cfg = self.config
        headers: dict[str, str] = {}
        if caller:  # names the client this session calls for
            headers[self.settings.client_id_header] = caller
        if auth_header:
            headers.update(auth_header)
        hdrs = headers or None
        if cfg.transport == "sse":
            return sse_client(cfg.url, headers=hdrs, timeout=cfg.timeout_seconds)
        http_client = create_mcp_http_client(headers=hdrs)
        stack.push_async_callback(http_client.aclose)
        return streamable_http_client(cfg.url, http_client=http_client)

    def _new_client(
        self, stack: AsyncExitStack, caller: str | None = None, auth_header: dict[str, str] | None = None
    ) -> Client:
        return Client(
            self._transport(stack, caller, auth_header),
            read_timeout_seconds=self.config.timeout_seconds,
            client_info=types.Implementation(name=self.settings.name, version=self.settings.version),
            cache=None,
        )

    async def run(self) -> None:
        """Supervisor loop: connect, serve, reconnect forever (until cancelled)."""
        delay = self.settings.reconnect_initial_delay
        force_token = False  # after a failed attempt, refetch the oauth2 token in case it was rejected/expired
        while True:
            try:
                async with AsyncExitStack() as stack:
                    auth_header = await self._authorization(force=force_token)
                    force_token = False
                    client = self._new_client(stack, auth_header=auth_header)
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
                force_token = self._is_oauth()  # a rejected/expired token looks like any other failure; refetch next time
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
            with anyio.move_on_after(self.settings.health_check_interval):
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
            logger.info("'%s' closed its change stream; polling every %.0fs", self.name, self.settings.health_check_interval)
        except (ListenNotSupportedError, MCPError) as exc:
            logger.info("'%s' can't stream changes (%s); polling every %.0fs", self.name, exc, self.settings.health_check_interval)
        except SubscriptionLost as exc:
            logger.warning("Change stream from '%s' dropped: %s", self.name, exc)
            self.mark_broken()  # reconnecting re-opens the stream

    async def _apply_changes(self) -> None:
        """Re-list once per burst of change events."""
        while True:
            await self._changed.wait()
            await anyio.sleep(self.settings.change_debounce)  # events arriving meanwhile are folded into this refresh
            self._changed = anyio.Event()
            try:
                with anyio.fail_after(self.config.timeout_seconds):
                    await self.refresh_catalog(force=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Refresh of '%s' after a change failed: %s", self.name, exc)
                self.mark_broken()

    def mark_broken(self) -> None:
        self._broken.set()

    def update_filters(self, config: UpstreamConfig) -> None:
        """Take new include/exclude tool lists. The connection is kept; the catalog is re-listed so clients
        see the change at once (when not connected, the next connect uses the new filters anyway)."""
        self.config = config
        if self.client is not None:
            self._changed.set()

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
                auth_header = await self._authorization()  # reuses the cached oauth2 token the shared session fetched
                client = self._new_client(stack, caller, auth_header)
                await stack.enter_async_context(client)
                session.client = client
                session.ready.set()
                logger.info("Opened session to '%s' for client '%s'", self.name, caller)
                while (idle := time.monotonic() - session.last_used) < self.settings.client_session_idle:
                    with anyio.move_on_after(self.settings.client_session_idle - idle):
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
        if not force and time.monotonic() - self.catalog.fetched_at < self.settings.catalog_ttl:
            return
        async with self._refresh_lock:
            if not force and time.monotonic() - self.catalog.fetched_at < self.settings.catalog_ttl:
                return
            client = self.require_client()
            caps = client.server_capabilities
            catalog = Catalog(fetched_at=time.monotonic())
            all_tools: list[types.Tool] = []
            if caps.tools is not None:
                all_tools = await _collect(client.list_tools, "tools")
                catalog.tools = [t for t in all_tools if self.config.tool_allowed(t.name)]
            if caps.resources is not None:
                catalog.resources = await _collect(client.list_resources, "resources")
                catalog.resource_templates = await _collect(client.list_resource_templates, "resource_templates")
            if caps.prompts is not None:
                catalog.prompts = await _collect(client.list_prompts, "prompts")
            self._set_catalog(catalog)
            self._report_tools(all_tools)

    def _report_tools(self, tools: list[types.Tool]) -> None:
        """Only after a successful list: a server that is down reports nothing, so its tools aren't marked
        removed."""
        mcp_id = self.config.id
        if self._on_tools is None or mcp_id is None or self._reported_tools == (mcp_id, tools):
            return
        self._reported_tools = (mcp_id, tools)
        self._on_tools(mcp_id, self.name, tools)

    def _set_catalog(self, catalog: Catalog) -> None:
        changes = catalog.changes_from(self.catalog)
        self.catalog = catalog
        if changes and self._on_change is not None:
            logger.info("'%s' changed: %s", self.name, ", ".join(type(c).__name__ for c in changes))
            self._on_change(self.name, changes)

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.config.enabled,
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


# Changing any of these means a new connection; the others (tool filters) apply to the open one.
# auth is here so editing a server's token/credentials reconnects with the new Authorization header.
_CONNECTION_FIELDS = ("url", "transport", "timeout_seconds", "auth")


class UpstreamPool:
    def __init__(
        self,
        configs: list[UpstreamConfig],
        settings: GatewaySettings,
        on_change: OnChange | None = None,
        on_tools: OnTools | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        self.settings = settings
        self._on_change = on_change
        self._on_tools = on_tools
        self._token_store = token_store  # shared across all upstreams for OAuth2 token caching
        self.upstreams: dict[str, Upstream] = {c.name: self._new(c) for c in configs}
        self._scopes: dict[str, anyio.CancelScope] = {}
        self._tg: anyio.abc.TaskGroup | None = None

    def _new(self, config: UpstreamConfig) -> Upstream:
        return Upstream(config, self.settings, self._on_change, self._on_tools, self._token_store)

    async def run(self) -> None:
        async with anyio.create_task_group() as tg:
            self._tg = tg
            for upstream in self.upstreams.values():
                self._start(upstream)
            try:
                await anyio.sleep_forever()
            finally:
                self._tg = None

    def _start(self, upstream: Upstream) -> None:
        assert self._tg is not None
        scope = self._scopes[upstream.name] = anyio.CancelScope()

        async def supervise() -> None:
            with scope:
                await upstream.run()

        self._tg.start_soon(supervise, name=f"upstream:{upstream.name}")

    def _stop(self, name: str) -> None:
        """Remove a server: it leaves every list at once, and its connection is closed."""
        self.upstreams.pop(name, None)
        scope = self._scopes.pop(name, None)
        if scope is not None:
            scope.cancel()  # its supervisor empties its catalog on the way out, which tells listening clients

    def apply(self, configs: list[UpstreamConfig]) -> None:
        """Make the running servers match `configs` (the live rows of the server table)."""
        if self._tg is None:  # not running yet: just replace the list
            self.upstreams = {c.name: self._new(c) for c in configs}
            return
        wanted = {c.name: c for c in configs}
        for name in [n for n in self.upstreams if n not in wanted]:
            logger.info("Server '%s' was deleted or renamed: disconnecting", name)
            self._stop(name)
        for name, config in wanted.items():
            current = self.upstreams.get(name)
            if current is None:
                logger.info("Server '%s' was added: connecting to %s", name, config.url)
            elif any(getattr(current.config, f) != getattr(config, f) for f in _CONNECTION_FIELDS):
                logger.info("Server '%s' changed its URL, transport or timeout: reconnecting", name)
                self._stop(name)
            else:
                if current.config != config:
                    old = current.config
                    if (old.include_tools, old.exclude_tools) != (config.include_tools, config.exclude_tools):
                        logger.info(
                            "Server '%s' tool filters changed: include=%s exclude=%s",
                            name,
                            config.include_tools,
                            config.exclude_tools,
                        )
                    if old.enabled != config.enabled:
                        logger.info(
                            "Server '%s' was %s",
                            name,
                            "enabled: open to every key allowed to use it"
                            if config.enabled
                            else "disabled: only the admin who registered it can use it now",
                        )
                        if not config.enabled:
                            self._announce(name)  # before the switch, so the clients losing it hear about it
                    current.update_filters(config)
                    if config.enabled and not old.enabled:
                        self._announce(name)  # after the switch, so the clients gaining it hear about it
                continue
            upstream = self.upstreams[name] = self._new(config)
            self._start(upstream)

    def _announce(self, name: str) -> None:
        """Tell listening clients that a server's lists changed, so they re-list (who may see it changed)."""
        if self._on_change is not None:
            self._on_change(name, [ToolsListChanged(), ResourcesListChanged(), PromptsListChanged()])

    async def wait_until_ready(self, timeout: float) -> None:
        """Give upstreams a moment to connect at startup so the first tools/list is complete."""
        with anyio.move_on_after(timeout):
            while not all(u.connected or u.last_error for u in self.upstreams.values()):
                await anyio.sleep(0.1)

    def get(self, name: str) -> Upstream | None:
        return self.upstreams.get(name)

    def status(self) -> list[dict[str, Any]]:
        return [u.status() for u in self.upstreams.values()]
