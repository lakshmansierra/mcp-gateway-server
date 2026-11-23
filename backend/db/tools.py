"""SQL for reading the tool table and its history (MCP_TOOL_TABLE and MCP_TOOL_CHANGE_TABLE in .env).

The gateway writes both: one row per tool a server has ever listed (a tool the server no longer lists has
removed_at set), and one history row per added / removed / changed tool. The backend only reads them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from hdbcli import dbapi

from backend.config import get_settings
from backend.db import servers, users


class ToolRow(NamedTuple):
    id: int
    server_id: int
    server_name: str
    tool_name: str
    description: str | None
    input_schema: str | None  # JSON text
    first_seen_at: datetime
    removed_at: datetime | None
    include_tools: str  # the server's filters, to tell whether the gateway hides the tool
    exclude_tools: str | None
    server_enabled: int
    server_is_deleted: int


class ChangeRow(NamedTuple):
    id: int
    tool_id: int
    change_type: str  # added / removed / changed
    changed_at: datetime
    old_value: str | None  # JSON: {"description": ..., "input_schema": ...}
    new_value: str | None


def table() -> str:
    s = get_settings()
    return s.table(s.tool_table)


def change_table() -> str:
    s = get_settings()
    return s.table(s.tool_change_table)


def text(value: Any) -> str | None:
    """NCLOB columns come back as LOB objects; read them into str."""
    if value is None or isinstance(value, str):
        return value
    return value.read()


def _row(row: tuple) -> ToolRow:
    return ToolRow(row[0], row[1], row[2], row[3], text(row[4]), text(row[5]), *row[6:])


def _managed_sql(where: str) -> str:
    """Tools of the servers the admin manages (parameters: admin id, admin id, then `where`'s)."""
    return (
        f'SELECT t."id", t."mcp_id", s."server_name", t."tool_name", t."description", t."input_schema", '
        f't."first_seen_at", t."removed_at", s."include_tools", s."exclude_tools", s."enabled", s."is_deleted" '
        f'FROM {table()} t JOIN {servers.table()} s ON s."id" = t."mcp_id" '
        f'WHERE s."user_id" IN ({users.managed_ids_sql()}) AND {where}'
    )


def list_managed(cur: dbapi.Cursor, admin_id: int, server_id: int | None = None) -> list[ToolRow]:
    """Every tool of the admin's servers (removed tools and tools of deleted servers included), by server and name.
    `server_id` narrows it to one server."""
    where, params = ('s."id" = ?', (server_id,)) if server_id is not None else ("1 = 1", ())
    cur.execute(
        _managed_sql(where) + ' ORDER BY s."server_name", t."tool_name"',
        (admin_id, admin_id, *params),
    )
    return [_row(row) for row in cur.fetchall()]


def get_managed(cur: dbapi.Cursor, tool_id: int, admin_id: int) -> ToolRow | None:
    """This tool if it belongs to a server the admin manages; else None."""
    cur.execute(_managed_sql('t."id" = ?'), (admin_id, admin_id, tool_id))
    row = cur.fetchone()
    return None if row is None else _row(row)


def list_live(cur: dbapi.Cursor, server_ids: list[int]) -> list[ToolRow]:
    """The tools these servers list now (removed ones left out), by server and name. The caller picks the servers
    and drops tools the server's filters hide."""
    if not server_ids:
        return []
    placeholders = ", ".join("?" for _ in server_ids)
    cur.execute(
        f'SELECT t."id", t."mcp_id", s."server_name", t."tool_name", t."description", t."input_schema", '
        f't."first_seen_at", t."removed_at", s."include_tools", s."exclude_tools", s."enabled", s."is_deleted" '
        f'FROM {table()} t JOIN {servers.table()} s ON s."id" = t."mcp_id" '
        f'WHERE t."mcp_id" IN ({placeholders}) AND t."removed_at" IS NULL ORDER BY s."server_name", t."tool_name"',
        tuple(server_ids),
    )
    return [_row(row) for row in cur.fetchall()]


def changes(cur: dbapi.Cursor, tool_id: int) -> list[ChangeRow]:
    """A tool's history, newest first. The caller checks that the admin may see the tool."""
    cur.execute(
        f'SELECT "id", "tool_id", "change_type", "changed_at", "old_value", "new_value" FROM {change_table()} '
        f'WHERE "tool_id" = ? ORDER BY "changed_at" DESC, "id" DESC',
        (tool_id,),
    )
    return [ChangeRow(*row[:4], text(row[4]), text(row[5])) for row in cur.fetchall()]
