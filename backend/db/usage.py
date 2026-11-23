"""SQL for reading tool calls (MCP_TOOL_CALL_TABLE in .env): call counts and the call log.

The gateway writes one row per tools/call (tool, key, user, called_at in UTC, duration_ms, status ok / error /
timeout, error_message). Who sees which calls is a Scope:
  admin_scope  calls to tools of the servers the admin manages (deleted servers and removed tools included)
  user_scope   the user's own calls, made with their live keys, to live tools of their admin's live servers
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from hdbcli import dbapi

from backend.config import get_settings
from backend.db import api_keys, servers, tools, users


@dataclass(frozen=True)
class Scope:
    """tools_sql limits the tools (t) and servers (s); calls_sql limits the calls (c). Each with its parameters."""

    tools_sql: str
    tools_params: tuple
    calls_sql: str = "1 = 1"
    calls_params: tuple = ()


def admin_scope(admin_id: int) -> Scope:
    return Scope(f's."user_id" IN ({users.managed_ids_sql()})', (admin_id, admin_id))


def user_scope(user_id: int, admin_id: int | None) -> Scope:
    """Nothing deleted or removed: only live tools of live servers of the user's admin, and only calls made with the
    user's live keys. A user without an admin sees nothing."""
    return Scope(
        tools_sql='s."user_id" = ? AND s."is_deleted" = 0 AND t."removed_at" IS NULL',
        tools_params=(-1 if admin_id is None else admin_id,),
        calls_sql=f'c."key_id" IN (SELECT "id" FROM {api_keys.table()} WHERE "user_id" = ? AND "is_deleted" = 0)',
        calls_params=(user_id,),
    )


@dataclass(frozen=True)
class CallFilter:
    """Optional narrowing of the calls; every field left as None means 'any'."""

    start: datetime | None = None  # called_at >= start (UTC, naive)
    end: datetime | None = None  # called_at < end
    server_id: int | None = None
    tool_id: int | None = None
    user_id: int | None = None
    key_id: int | None = None
    status: str | None = None

    def sql(self) -> tuple[str, tuple]:
        """Conditions on the call (c), its tool (t) and server (s), joined with AND, and their parameters."""
        parts: list[tuple[str, object]] = [
            ('c."called_at" >= ?', self.start),
            ('c."called_at" < ?', self.end),
            ('t."mcp_id" = ?', self.server_id),
            ('c."tool_id" = ?', self.tool_id),
            ('c."user_id" = ?', self.user_id),
            ('c."key_id" = ?', self.key_id),
            ('c."status" = ?', self.status),
        ]
        used = [(sql, value) for sql, value in parts if value is not None]
        return " AND ".join(["1 = 1", *(sql for sql, _ in used)]), tuple(value for _, value in used)


class ToolUsageRow(NamedTuple):
    tool_id: int
    tool_name: str
    removed_at: datetime | None
    server_id: int
    server_name: str
    include_tools: str  # the server's filters, so callers can tell hidden tools
    exclude_tools: str | None
    calls: int
    ok: int
    error: int
    timeout: int
    avg_duration_ms: float | None
    last_called_at: datetime | None


class GroupUsageRow(NamedTuple):
    """Counts for one account (by_user) or one key (by_key)."""

    id: int
    name: str | None
    type: str | None  # by_user: admin / user; by_key: None
    calls: int
    ok: int
    error: int
    timeout: int
    avg_duration_ms: float | None
    last_called_at: datetime | None


class CallRow(NamedTuple):
    id: int
    called_at: datetime
    server_id: int
    server_name: str
    tool_id: int
    tool_name: str
    key_id: int
    key_name: str | None
    user_id: int
    user_name: str | None
    duration_ms: int
    status: str
    error_message: str | None


def table() -> str:
    s = get_settings()
    return s.table(s.tool_call_table)


_STATS = (
    'COUNT(c."id"), '
    "COALESCE(SUM(CASE WHEN c.\"status\" = 'ok' THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN c.\"status\" = 'error' THEN 1 ELSE 0 END), 0), "
    "COALESCE(SUM(CASE WHEN c.\"status\" = 'timeout' THEN 1 ELSE 0 END), 0), "
    'AVG(CAST(c."duration_ms" AS DOUBLE)), MAX(c."called_at")'
)


def _calls_from() -> str:
    """Calls with their tool (t) and server (s)."""
    return (
        f'FROM {table()} c JOIN {tools.table()} t ON t."id" = c."tool_id" '
        f'JOIN {servers.table()} s ON s."id" = t."mcp_id" '
    )


def _where(scope: Scope, f: CallFilter) -> tuple[str, tuple]:
    filter_sql, filter_params = f.sql()
    return (
        f"WHERE ({scope.tools_sql}) AND ({scope.calls_sql}) AND {filter_sql} ",
        (*scope.tools_params, *scope.calls_params, *filter_params),
    )


def by_tool(cur: dbapi.Cursor, scope: Scope, f: CallFilter) -> list[ToolUsageRow]:
    """Every tool in the scope with its call counts (0 for tools never called), most called first.

    The call conditions go into the LEFT JOIN, so tools without matching calls still appear."""
    call_filter = CallFilter(start=f.start, end=f.end, user_id=f.user_id, key_id=f.key_id, status=f.status)
    on_sql, on_params = call_filter.sql()
    where, where_params = ('t."mcp_id" = ?', (f.server_id,)) if f.server_id is not None else ("1 = 1", ())
    if f.tool_id is not None:
        where, where_params = f'{where} AND t."id" = ?', (*where_params, f.tool_id)
    cur.execute(
        f'SELECT t."id", t."tool_name", t."removed_at", s."id", s."server_name", s."include_tools", s."exclude_tools", '
        f"{_STATS} "
        f'FROM {tools.table()} t JOIN {servers.table()} s ON s."id" = t."mcp_id" '
        f'LEFT JOIN {table()} c ON c."tool_id" = t."id" AND {on_sql} AND ({scope.calls_sql}) '
        f"WHERE ({scope.tools_sql}) AND {where} "
        f'GROUP BY t."id", t."tool_name", t."removed_at", s."id", s."server_name", s."include_tools", s."exclude_tools" '
        f'ORDER BY COUNT(c."id") DESC, s."server_name", t."tool_name"',
        (*on_params, *scope.calls_params, *scope.tools_params, *where_params),
    )
    return [ToolUsageRow(*row) for row in cur.fetchall()]


def by_user(cur: dbapi.Cursor, scope: Scope, f: CallFilter) -> list[GroupUsageRow]:
    """Who made the calls in the scope, most calls first (only accounts with at least one call)."""
    where, params = _where(scope, f)
    cur.execute(
        f'SELECT c."user_id", u."user_name", u."type", {_STATS} {_calls_from()}'
        f'LEFT JOIN {users.table()} u ON u."id" = c."user_id" {where}'
        f'GROUP BY c."user_id", u."user_name", u."type" ORDER BY COUNT(c."id") DESC, u."user_name"',
        params,
    )
    return [GroupUsageRow(*row) for row in cur.fetchall()]


def by_key(cur: dbapi.Cursor, scope: Scope, f: CallFilter) -> list[GroupUsageRow]:
    """Which keys made the calls in the scope, most calls first (only keys with at least one call)."""
    where, params = _where(scope, f)
    cur.execute(
        f'SELECT c."key_id", k."key_name", NULL, {_STATS} {_calls_from()}'
        f'LEFT JOIN {api_keys.table()} k ON k."id" = c."key_id" {where}'
        f'GROUP BY c."key_id", k."key_name" ORDER BY COUNT(c."id") DESC, k."key_name"',
        params,
    )
    return [GroupUsageRow(*row) for row in cur.fetchall()]


def calls(cur: dbapi.Cursor, scope: Scope, f: CallFilter, limit: int, offset: int) -> tuple[int, list[CallRow]]:
    """One page of the call log, newest first, and how many calls match in all."""
    where, params = _where(scope, f)
    cur.execute(f"SELECT COUNT(*) {_calls_from()}{where}", params)
    total = cur.fetchone()[0]
    cur.execute(
        f'SELECT c."id", c."called_at", s."id", s."server_name", t."id", t."tool_name", c."key_id", k."key_name", '
        f'c."user_id", u."user_name", c."duration_ms", c."status", c."error_message" '
        f'{_calls_from()}LEFT JOIN {api_keys.table()} k ON k."id" = c."key_id" '
        f'LEFT JOIN {users.table()} u ON u."id" = c."user_id" {where}'
        f'ORDER BY c."called_at" DESC, c."id" DESC LIMIT ? OFFSET ?',
        (*params, limit, offset),
    )
    return total, [CallRow(*row) for row in cur.fetchall()]
