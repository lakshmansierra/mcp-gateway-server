"""What a user (not an admin) sees: the servers they may use, their keys, the tools they can call, and their own
tool usage (read-only).

Nothing deleted or removed ever appears: no deleted servers (not even their names), no deleted keys, no tools a
server stopped listing, and no tools the admin's include/exclude filters hide. A server id outside what the user
may use answers 404.
"""

from __future__ import annotations

from hdbcli import dbapi

from backend.db import api_keys, servers, tools, usage
from backend.models import (
    CallPageOut,
    KeyUsageOut,
    MyUsageSummaryOut,
    UserKeyOut,
    UserKeyServerOut,
    UserOut,
    UserServerOut,
    UserToolOut,
)
from backend.services.admin_views import (
    call_page,
    db_cursor,
    gateway_name,
    group_counts,
    is_hidden,
    json_value,
    not_found,
    per_server_and_total,
    tool_usage,
)


def _visible_tools(cur: dbapi.Cursor, server_ids: list[int]) -> list[tools.ToolRow]:
    return [
        t for t in tools.list_live(cur, server_ids) if not is_hidden(t.tool_name, t.include_tools, t.exclude_tools)
    ]


def _tool(t: tools.ToolRow) -> UserToolOut:
    return UserToolOut(
        id=t.id,
        server_id=t.server_id,
        server_name=t.server_name,
        tool_name=t.tool_name,
        gateway_name=gateway_name(t.server_name, t.tool_name),
        description=t.description,
        input_schema=json_value(t.input_schema),
        first_seen_at=t.first_seen_at,
    )


def list_servers(conn: dbapi.Connection, me: UserOut) -> list[UserServerOut]:
    """Servers added by the user's admin, enabled and not deleted, with how many tools the user can call on each."""
    with db_cursor(conn) as cur:
        rows = servers.list_usable(cur, me.created_by)
        visible = _visible_tools(cur, [r.id for r in rows])
    counts: dict[int, int] = {}
    for t in visible:
        counts[t.server_id] = counts.get(t.server_id, 0) + 1
    return [
        UserServerOut(id=r.id, server_name=r.server_name, tool_count=counts.get(r.id, 0), created_at=r.created_at)
        for r in rows
    ]


def list_tools(conn: dbapi.Connection, me: UserOut, server_id: int | None = None) -> list[UserToolOut]:
    """The tools the user can call, on every usable server or on one (404 if the user can't use it)."""
    with db_cursor(conn) as cur:
        usable = [r.id for r in servers.list_usable(cur, me.created_by)]
        if server_id is not None:
            if server_id not in usable:
                raise not_found(f"Server {server_id}")
            usable = [server_id]
        return [_tool(t) for t in _visible_tools(cur, usable)]


def list_keys(conn: dbapi.Connection, me: UserOut) -> list[UserKeyOut]:
    """The user's live keys. Each lists its servers that aren't deleted; disabled ones carry enabled = false."""
    with db_cursor(conn) as cur:
        rows = api_keys.list_own_live(cur, me.id)
        mapped = api_keys.mapped_servers(cur, [r.id for r in rows])
    return [
        UserKeyOut(
            id=r.id,
            key_name=r.key_name,
            servers=[
                UserKeyServerOut(id=s.id, server_name=s.server_name, enabled=bool(s.enabled))
                for s in mapped.get(r.id, [])
                if not s.is_deleted
            ],
            created_at=r.created_at,
        )
        for r in rows
    ]


def usage_summary(conn: dbapi.Connection, me: UserOut, f: usage.CallFilter) -> MyUsageSummaryOut:
    """The user's own calls, counted in total, per server, per tool and per key.

    by_tool lists every live tool of the user's admin's live servers, called or not, except tools the filters hide
    that the user never called."""
    scope = usage.user_scope(me.id, me.created_by)
    with db_cursor(conn) as cur:
        tool_rows = [
            r
            for r in usage.by_tool(cur, scope, f)
            if r.calls or not is_hidden(r.tool_name, r.include_tools, r.exclude_tools)
        ]
        key_rows = usage.by_key(cur, scope, f)
    by_server, total = per_server_and_total(tool_rows)
    by_key = [KeyUsageOut(key_id=r.id, key_name=r.name, **group_counts(r)) for r in key_rows]
    return MyUsageSummaryOut(
        start=f.start, end=f.end, by_server=by_server, by_tool=tool_usage(tool_rows), by_key=by_key, **total
    )


def call_log(conn: dbapi.Connection, me: UserOut, f: usage.CallFilter, limit: int, offset: int) -> CallPageOut:
    return call_page(conn, usage.user_scope(me.id, me.created_by), f, limit, offset)
