"""The gateway MCP server: aggregates every upstream's tools, resources and prompts.

Naming: tools and prompts are exposed as `<upstream>__<name>` so two upstreams can
both offer e.g. `search` without colliding. Resource URIs are passed through
unchanged and routed back to the upstream that listed them.

Change notifications: clients can open a `subscriptions/listen` stream. When a server's
tools, resources or prompts change, the gateway tells each listening client, but only
if its API key may use that server, so no client learns about servers it can't reach.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import anyio
import mcp_types as types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.subscriptions import ListenHandler
from mcp.shared.exceptions import MCPError
from mcp.shared.subscriptions import ServerEvent

from gateway.auth import api_key_from_request
from gateway.config import NAME_SEPARATOR, ApiKeyConfig, GatewayConfig
from gateway.upstream import Upstream, UpstreamPool, UpstreamUnavailableError

logger = logging.getLogger(__name__)

STARTUP_CONNECT_TIMEOUT = 10.0

T = TypeVar("T")


def prefixed(upstream: str, name: str) -> str:
    return f"{upstream}{NAME_SEPARATOR}{name}"


def split_prefixed(name: str) -> tuple[str, str]:
    upstream, sep, original = name.partition(NAME_SEPARATOR)
    if not sep or not original:
        raise MCPError(types.INVALID_PARAMS, f"Unknown name '{name}': expected '<server>{NAME_SEPARATOR}<name>'")
    return upstream, original


def _template_regex(uri_template: str) -> re.Pattern[str]:
    """Rough RFC 6570 matcher: each {var} matches one or more non-empty characters."""
    parts = re.split(r"\{[^}]+\}", uri_template)
    return re.compile("^" + ".+?".join(re.escape(p) for p in parts) + "$")


class ChangeBus:
    """Fans catalog changes out to the clients' listen streams, tagged with the server they came from."""

    def __init__(self) -> None:
        self._listeners: dict[object, Callable[[str, ServerEvent], None]] = {}

    def publish(self, upstream: str, events: list[ServerEvent]) -> None:
        for listener in list(self._listeners.values()):
            for event in events:
                listener(upstream, event)

    def subscribe(self, listener: Callable[[str, ServerEvent], None]) -> Callable[[], None]:
        token = object()
        self._listeners[token] = listener
        return lambda: self._listeners.pop(token, None)


class _ChangesVisibleTo:
    """The bus one client's listen stream reads: only changes from servers its key may use."""

    def __init__(self, bus: ChangeBus, key: ApiKeyConfig | None) -> None:
        self._bus = bus
        self._key = key

    async def publish(self, event: ServerEvent) -> None:  # part of SubscriptionBus; the gateway publishes via ChangeBus
        raise NotImplementedError

    def subscribe(self, listener: Callable[[ServerEvent], None]) -> Callable[[], None]:
        def deliver(upstream: str, event: ServerEvent) -> None:
            if self._key is None or self._key.can_access(upstream):
                listener(event)

        return self._bus.subscribe(deliver)


class Gateway:
    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.changes = ChangeBus()
        self.pool = UpstreamPool(config.enabled_upstreams, config.gateway, on_change=self.changes.publish)

    # ---- access control ---------------------------------------------------

    def _visible(self, ctx: ServerRequestContext[Any, Any]) -> list[Upstream]:
        key = api_key_from_request(ctx.request)
        return [u for u in self.pool.upstreams.values() if u.connected and (key is None or key.can_access(u.name))]

    def _resolve(self, ctx: ServerRequestContext[Any, Any], upstream_name: str) -> Upstream:
        upstream = self.pool.get(upstream_name)
        key = api_key_from_request(ctx.request)
        if upstream is None or (key is not None and not key.can_access(upstream_name)):
            raise MCPError(types.INVALID_PARAMS, f"Unknown MCP server '{upstream_name}'")
        return upstream

    async def _gather(
        self, ctx: ServerRequestContext[Any, Any], pick: Callable[[Upstream], Iterable[T]]
    ) -> list[tuple[Upstream, T]]:
        """Refresh each visible upstream's catalog concurrently and collect items from it."""
        upstreams = self._visible(ctx)

        async def refresh(u: Upstream) -> None:
            try:
                await u.refresh_catalog()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Catalog refresh failed for '%s': %s", u.name, exc)
                u.mark_broken()

        async with anyio.create_task_group() as tg:
            for u in upstreams:
                tg.start_soon(refresh, u)
        return [(u, item) for u in upstreams if u.connected for item in pick(u)]

    async def _forward(
        self, ctx: ServerRequestContext[Any, Any], upstream: Upstream, call: Callable[[Any], Any]
    ) -> Any:
        """Run a call on the caller's own session to the upstream; transport failures trigger a reconnect."""
        caller = _client_id(ctx)
        client = await upstream.client_for(caller)
        try:
            return await call(client)
        except MCPError:
            raise
        except Exception as exc:
            logger.warning("Request to '%s' failed: %s", upstream.name, exc)
            upstream.close_client(caller)
            upstream.mark_broken()
            raise UpstreamUnavailableError(f"Upstream '{upstream.name}' failed: {exc}") from exc

    # ---- tools ------------------------------------------------------------

    async def list_tools(
        self, ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        items = await self._gather(ctx, lambda u: u.catalog.tools)
        tools = [
            tool.model_copy(
                update={
                    "name": prefixed(u.name, tool.name),
                    "description": f"[{u.name}] {tool.description or ''}".strip(),
                }
            )
            for u, tool in items
        ]
        return types.ListToolsResult(tools=tools)

    async def call_tool(
        self, ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        upstream_name, tool = split_prefixed(params.name)
        upstream = self._resolve(ctx, upstream_name)
        if not upstream.config.tool_allowed(tool):
            raise MCPError(types.INVALID_PARAMS, f"Tool '{params.name}' is not exposed by this gateway")
        logger.info("tools/call %s -> %s.%s", _caller(ctx), upstream_name, tool)
        try:
            return await self._forward(ctx, upstream, lambda c: c.call_tool(tool, params.arguments))
        except UpstreamUnavailableError as exc:
            return types.CallToolResult(content=[types.TextContent(text=str(exc))], is_error=True)

    # ---- resources --------------------------------------------------------

    async def list_resources(
        self, ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListResourcesResult:
        items = await self._gather(ctx, lambda u: u.catalog.resources)
        return types.ListResourcesResult(resources=[r for _, r in items])

    async def list_resource_templates(
        self, ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListResourceTemplatesResult:
        items = await self._gather(ctx, lambda u: u.catalog.resource_templates)
        return types.ListResourceTemplatesResult(resource_templates=[t for _, t in items])

    def _owner_of_uri(self, ctx: ServerRequestContext[Any, Any], uri: str) -> Upstream:
        visible = self._visible(ctx)
        for u in visible:
            if any(str(r.uri) == uri for r in u.catalog.resources):
                return u
        for u in visible:
            if any(_template_regex(t.uri_template).match(uri) for t in u.catalog.resource_templates):
                return u
        raise MCPError(types.INVALID_PARAMS, f"No connected MCP server provides resource '{uri}'")

    async def read_resource(
        self, ctx: ServerRequestContext[Any, Any], params: types.ReadResourceRequestParams
    ) -> types.ReadResourceResult:
        uri = str(params.uri)
        try:
            upstream = self._owner_of_uri(ctx, uri)
        except MCPError:
            await self._gather(ctx, lambda u: ())  # catalog may be stale; refresh and retry once
            upstream = self._owner_of_uri(ctx, uri)
        return await self._forward_or_error(ctx, upstream, lambda c: c.read_resource(uri))

    # ---- prompts ----------------------------------------------------------

    async def list_prompts(
        self, ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListPromptsResult:
        items = await self._gather(ctx, lambda u: u.catalog.prompts)
        prompts = [p.model_copy(update={"name": prefixed(u.name, p.name)}) for u, p in items]
        return types.ListPromptsResult(prompts=prompts)

    async def get_prompt(
        self, ctx: ServerRequestContext[Any, Any], params: types.GetPromptRequestParams
    ) -> types.GetPromptResult:
        upstream_name, prompt = split_prefixed(params.name)
        upstream = self._resolve(ctx, upstream_name)
        return await self._forward_or_error(ctx, upstream, lambda c: c.get_prompt(prompt, params.arguments))

    # ---- completion -------------------------------------------------------

    async def complete(
        self, ctx: ServerRequestContext[Any, Any], params: types.CompleteRequestParams
    ) -> types.CompleteResult:
        ref = params.ref
        if isinstance(ref, types.PromptReference):
            upstream_name, original = split_prefixed(ref.name)
            upstream = self._resolve(ctx, upstream_name)
            ref = ref.model_copy(update={"name": original})
        else:
            upstream = self._owner_of_uri(ctx, ref.uri)
        context_args = params.context.arguments if params.context else None
        argument = {"name": params.argument.name, "value": params.argument.value}
        return await self._forward_or_error(ctx, upstream, lambda c: c.complete(ref, argument, context_args))

    # ---- change notifications ---------------------------------------------

    async def listen(
        self, ctx: ServerRequestContext[Any, Any], params: types.SubscriptionsListenRequestParams
    ) -> types.SubscriptionsListenResult:
        """Serve one client's change stream, limited to the servers its key may use."""
        logger.info("subscriptions/listen opened by %s", _caller(ctx))
        handler = ListenHandler(_ChangesVisibleTo(self.changes, api_key_from_request(ctx.request)))
        return await handler(ctx, params)

    async def _forward_or_error(
        self, ctx: ServerRequestContext[Any, Any], upstream: Upstream, call: Callable[[Any], Any]
    ) -> Any:
        try:
            return await self._forward(ctx, upstream, call)
        except UpstreamUnavailableError as exc:
            raise MCPError(types.INTERNAL_ERROR, str(exc)) from exc


def _client_id(ctx: ServerRequestContext[Any, Any]) -> str | None:
    """The calling client's identity (its API key name), or None when auth is off (stdio, GATEWAY_AUTH_ENABLED=false)."""
    key = api_key_from_request(ctx.request)
    return key.name if key else None


def _caller(ctx: ServerRequestContext[Any, Any]) -> str:
    return _client_id(ctx) or "local"


def build_server(gateway: Gateway) -> Server[Any]:
    @asynccontextmanager
    async def lifespan(_: Server[Any]) -> AsyncIterator[dict[str, Any]]:
        async with anyio.create_task_group() as tg:
            tg.start_soon(gateway.pool.run)
            await gateway.pool.wait_until_ready(STARTUP_CONNECT_TIMEOUT)
            try:
                yield {"gateway": gateway}
            finally:
                tg.cancel_scope.cancel()

    upstream_names = ", ".join(gateway.pool.upstreams) or "none"
    return Server(
        gateway.config.gateway.name,
        version="1.0.0",
        instructions=(
            "This gateway aggregates several MCP servers. Tool and prompt names are "
            f"prefixed with their server name and '{NAME_SEPARATOR}'. Connected servers: {upstream_names}."
        ),
        lifespan=lifespan,
        on_list_tools=gateway.list_tools,
        on_call_tool=gateway.call_tool,
        on_list_resources=gateway.list_resources,
        on_list_resource_templates=gateway.list_resource_templates,
        on_read_resource=gateway.read_resource,
        on_list_prompts=gateway.list_prompts,
        on_get_prompt=gateway.get_prompt,
        on_completion=gateway.complete,
        on_subscriptions_listen=gateway.listen,
    )
