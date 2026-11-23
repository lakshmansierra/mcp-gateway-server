"""What an admin sees: their servers, users, keys, tools, tool history and tool usage (read-only).

Every query is limited to what the admin manages: the admin's own rows and rows of users they created (the same rule
as services/ownership.py). An id outside that answers 404, exactly like an id that doesn't exist, so an admin can't
tell another admin's servers, users or keys apart from missing ones. Deleted rows are included and tagged
(is_deleted, deleted_by, deleted_at); tools a server no longer lists are tagged with is_removed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import api_keys, servers, tools, usage, users
from backend.models import (
    CallOut,
    CallPageOut,
    KeyListOut,
    KeyServerOut,
    ServerListOut,
    ServerUsageOut,
    ToolChangeOut,
    ToolOut,
    ToolUsageOut,
    UsageSummaryOut,
    UserDetailOut,
    UserListOut,
    UserOut,
    UserUsageOut,
)
from backend.models.server import ALL_TOOLS, NAME_SEPARATOR, split_tools
from backend.services.servers import to_out as server_out


@contextmanager
def db_cursor(conn: dbapi.Connection) -> Iterator[dbapi.Cursor]:
    cur = conn.cursor()
    try:
        yield cur
    except dbapi.Error as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def json_value(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return value  # not JSON after all: show the text as stored


def gateway_name(server_name: str, tool_name: str) -> str:
    return f"{server_name}{NAME_SEPARATOR}{tool_name}"


def utc_naive(value: datetime | None) -> datetime | None:
    """called_at is stored in UTC without a time zone; a time sent with a zone is converted to that."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


# ---- servers ----


def _server(row: servers.ServerListRow) -> ServerListOut:
    return ServerListOut(
        **server_out(row.server).model_dump(),
        is_deleted=bool(row.is_deleted),
        deleted_by=row.deleted_by,
        deleted_at=row.deleted_at,
        tool_count=row.tool_count,
    )


def list_servers(conn: dbapi.Connection, admin: UserOut) -> list[ServerListOut]:
    with db_cursor(conn) as cur:
        return [_server(row) for row in servers.list_managed(cur, admin.id)]


def get_server(conn: dbapi.Connection, server_id: int, admin: UserOut) -> ServerListOut:
    with db_cursor(conn) as cur:
        row = servers.get_managed(cur, server_id, admin.id)
    if row is None:
        raise not_found(f"Server {server_id}")
    return _server(row)


# ---- tools ----


def is_hidden(tool_name: str, include_tools: str, exclude_tools: str | None) -> bool:
    """True if the server's filters keep the tool from clients (the gateway's rule: UpstreamConfig.tool_allowed)."""
    include = split_tools(include_tools)
    return tool_name in split_tools(exclude_tools) or not (ALL_TOOLS in include or tool_name in include)


def _tool(row: tools.ToolRow) -> ToolOut:
    hidden = is_hidden(row.tool_name, row.include_tools, row.exclude_tools)
    return ToolOut(
        id=row.id,
        server_id=row.server_id,
        server_name=row.server_name,
        tool_name=row.tool_name,
        gateway_name=gateway_name(row.server_name, row.tool_name),
        description=row.description,
        input_schema=json_value(row.input_schema),
        first_seen_at=row.first_seen_at,
        is_removed=row.removed_at is not None,
        removed_at=row.removed_at,
        hidden=hidden,
        server_enabled=bool(row.server_enabled),
        server_is_deleted=bool(row.server_is_deleted),
    )


def list_tools(conn: dbapi.Connection, admin: UserOut, server_id: int | None = None) -> list[ToolOut]:
    """All tools of the admin's servers, or of one server (404 if the admin doesn't manage it)."""
    with db_cursor(conn) as cur:
        if server_id is not None and servers.get_managed(cur, server_id, admin.id) is None:
            raise not_found(f"Server {server_id}")
        return [_tool(row) for row in tools.list_managed(cur, admin.id, server_id)]


def get_tool(conn: dbapi.Connection, tool_id: int, admin: UserOut) -> ToolOut:
    with db_cursor(conn) as cur:
        row = tools.get_managed(cur, tool_id, admin.id)
    if row is None:
        raise not_found(f"Tool {tool_id}")
    return _tool(row)


def tool_changes(conn: dbapi.Connection, tool_id: int, admin: UserOut) -> list[ToolChangeOut]:
    with db_cursor(conn) as cur:
        if tools.get_managed(cur, tool_id, admin.id) is None:
            raise not_found(f"Tool {tool_id}")
        rows = tools.changes(cur, tool_id)
    return [
        ToolChangeOut(
            id=r.id,
            tool_id=r.tool_id,
            change_type=r.change_type,
            changed_at=r.changed_at,
            old_value=json_value(r.old_value),
            new_value=json_value(r.new_value),
        )
        for r in rows
    ]


# ---- users and keys ----


def _keys(cur: dbapi.Cursor, rows: list[api_keys.KeyListRow]) -> list[KeyListOut]:
    mapped = api_keys.mapped_servers(cur, [r.id for r in rows if not r.all_servers])
    return [
        KeyListOut(
            id=r.id,
            user_id=r.user_id,
            user_name=r.user_name,
            owner_type=r.owner_type,
            key_name=r.key_name,
            all_servers=bool(r.all_servers),
            servers=[
                KeyServerOut(id=s.id, server_name=s.server_name, enabled=bool(s.enabled), is_deleted=bool(s.is_deleted))
                for s in mapped.get(r.id, [])
            ],
            created_at=r.created_at,
            is_deleted=bool(r.is_deleted),
            deleted_by=r.deleted_by,
            deleted_at=r.deleted_at,
        )
        for r in rows
    ]


def _user(row: users.UserListRow) -> UserListOut:
    return UserListOut(**row._asdict() | {"is_deleted": bool(row.is_deleted)})


def list_users(conn: dbapi.Connection, admin: UserOut) -> list[UserListOut]:
    with db_cursor(conn) as cur:
        return [_user(row) for row in users.list_created_by(cur, admin.id)]


def get_user(conn: dbapi.Connection, user_id: int, admin: UserOut) -> UserDetailOut:
    """A user the admin created (or the admin themselves) with all their keys."""
    with db_cursor(conn) as cur:
        row = users.get_managed(cur, user_id, admin.id)
        if row is None:
            raise not_found(f"User {user_id}")
        keys = _keys(cur, api_keys.list_managed(cur, admin.id, user_id))
    return UserDetailOut(**_user(row).model_dump(), keys=keys)


def list_keys(conn: dbapi.Connection, admin: UserOut, user_id: int | None = None) -> list[KeyListOut]:
    """The admin's own keys and their users' keys; `user_id` narrows it to one owner (404 if not theirs)."""
    with db_cursor(conn) as cur:
        if user_id is not None and users.get_managed(cur, user_id, admin.id) is None:
            raise not_found(f"User {user_id}")
        return _keys(cur, api_keys.list_managed(cur, admin.id, user_id))


def get_key(conn: dbapi.Connection, key_id: int, admin: UserOut) -> KeyListOut:
    with db_cursor(conn) as cur:
        row = api_keys.get_managed(cur, key_id, admin.id)
        if row is None:
            raise not_found(f"API key {key_id}")
        return _keys(cur, [row])[0]


# ---- usage (the user side reuses these helpers: services/user_views.py) ----


def _avg(total_ms: float, calls: int) -> float | None:
    return round(total_ms / calls, 1) if calls else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def tool_usage(rows: list[usage.ToolUsageRow]) -> list[ToolUsageOut]:
    return [
        ToolUsageOut(
            tool_id=r.tool_id,
            tool_name=r.tool_name,
            gateway_name=gateway_name(r.server_name, r.tool_name),
            is_removed=r.removed_at is not None,
            server_id=r.server_id,
            server_name=r.server_name,
            calls=r.calls,
            ok=r.ok,
            error=r.error,
            timeout=r.timeout,
            avg_duration_ms=_round(r.avg_duration_ms),
            last_called_at=r.last_called_at,
        )
        for r in rows
    ]


def group_counts(r: usage.GroupUsageRow) -> dict[str, Any]:
    return {
        "calls": r.calls,
        "ok": r.ok,
        "error": r.error,
        "timeout": r.timeout,
        "avg_duration_ms": _round(r.avg_duration_ms),
        "last_called_at": r.last_called_at,
    }


def per_server_and_total(rows: list[usage.ToolUsageRow]) -> tuple[list[ServerUsageOut], dict[str, Any]]:
    """Add up the tools per server and in total (the average is weighted by each tool's calls)."""
    servers_seen: dict[int, dict[str, Any]] = {}
    total = {"calls": 0, "ok": 0, "error": 0, "timeout": 0, "ms": 0.0, "last_called_at": None}
    for t in rows:
        s = servers_seen.setdefault(
            t.server_id,
            {"server_name": t.server_name, "calls": 0, "ok": 0, "error": 0, "timeout": 0, "ms": 0.0, "last_called_at": None},
        )
        for acc in (s, total):
            for k in ("calls", "ok", "error", "timeout"):
                acc[k] += getattr(t, k)
            acc["ms"] += (t.avg_duration_ms or 0) * t.calls
            if t.last_called_at and (acc["last_called_at"] is None or t.last_called_at > acc["last_called_at"]):
                acc["last_called_at"] = t.last_called_at

    def counts(acc: dict[str, Any]) -> dict[str, Any]:
        return {
            "calls": acc["calls"],
            "ok": acc["ok"],
            "error": acc["error"],
            "timeout": acc["timeout"],
            "avg_duration_ms": _avg(acc["ms"], acc["calls"]),
            "last_called_at": acc["last_called_at"],
        }

    by_server = sorted(
        (ServerUsageOut(server_id=sid, server_name=s["server_name"], **counts(s)) for sid, s in servers_seen.items()),
        key=lambda s: (-s.calls, s.server_name),
    )
    return by_server, counts(total)


def call_page(
    conn: dbapi.Connection, scope: usage.Scope, f: usage.CallFilter, limit: int, offset: int
) -> CallPageOut:
    with db_cursor(conn) as cur:
        total, rows = usage.calls(cur, scope, f, limit, offset)
    items = [CallOut(**r._asdict(), gateway_name=gateway_name(r.server_name, r.tool_name)) for r in rows]
    return CallPageOut(total=total, limit=limit, offset=offset, items=items)


def usage_summary(conn: dbapi.Connection, admin: UserOut, f: usage.CallFilter) -> UsageSummaryOut:
    """Call counts per server, per tool (every tool, called or not) and per account, over the filtered calls."""
    scope = usage.admin_scope(admin.id)
    with db_cursor(conn) as cur:
        tool_rows = usage.by_tool(cur, scope, f)
        user_rows = usage.by_user(cur, scope, f)
    by_server, total = per_server_and_total(tool_rows)
    by_user = [UserUsageOut(user_id=r.id, user_name=r.name, type=r.type, **group_counts(r)) for r in user_rows]
    return UsageSummaryOut(
        start=f.start, end=f.end, by_server=by_server, by_tool=tool_usage(tool_rows), by_user=by_user, **total
    )


def call_log(conn: dbapi.Connection, admin: UserOut, f: usage.CallFilter, limit: int, offset: int) -> CallPageOut:
    return call_page(conn, usage.admin_scope(admin.id), f, limit, offset)
