"""SQL for the MCP server table (MCP_SERVER_TABLE in .env)."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from hdbcli import dbapi

from backend.config import get_settings
from backend.db import users

_COLUMNS = (
    '"id", "user_id", "server_name", "server_url", "transport", "timeout_seconds", '
    '"enabled", "include_tools", "exclude_tools", "created_at"'
)


class ServerRow(NamedTuple):
    id: int
    user_id: int
    server_name: str
    server_url: str
    transport: str
    timeout_seconds: int
    enabled: int
    include_tools: str
    exclude_tools: str | None
    created_at: datetime


def _table() -> str:
    s = get_settings()
    return s.table(s.server_table)


def table() -> str:
    return _table()


class ServerListRow(NamedTuple):
    server: ServerRow
    is_deleted: int
    deleted_by: int | None
    deleted_at: datetime | None
    tool_count: int  # tools the server lists now (as the gateway last saw them)


def _managed_sql(where: str) -> str:
    """Servers added by the admin or by users the admin created (parameters: admin id, admin id, then `where`'s)."""
    s = get_settings()
    columns = ", ".join(f"s.{c.strip()}" for c in _COLUMNS.split(","))
    return (
        f'SELECT {columns}, s."is_deleted", s."deleted_by", s."deleted_at", '
        f'(SELECT COUNT(*) FROM {s.table(s.tool_table)} t WHERE t."mcp_id" = s."id" AND t."removed_at" IS NULL) '
        f'FROM {_table()} s WHERE s."user_id" IN ({users.managed_ids_sql()}) AND {where}'
    )


def _list_row(row: tuple) -> ServerListRow:
    return ServerListRow(ServerRow(*row[:10]), *row[10:])


def list_managed(cur: dbapi.Cursor, admin_id: int) -> list[ServerListRow]:
    """Every server this admin manages, deleted and disabled ones included, newest first."""
    cur.execute(_managed_sql("1 = 1") + ' ORDER BY s."id" DESC', (admin_id, admin_id))
    return [_list_row(row) for row in cur.fetchall()]


def get_managed(cur: dbapi.Cursor, server_id: int, admin_id: int) -> ServerListRow | None:
    """This server if the admin manages it, deleted or not; else None."""
    cur.execute(_managed_sql('s."id" = ?'), (admin_id, admin_id, server_id))
    row = cur.fetchone()
    return None if row is None else _list_row(row)


def list_usable(cur: dbapi.Cursor, admin_id: int | None) -> list[ServerRow]:
    """The servers a user may use: added by their admin (admin_id), enabled and not deleted, by name.
    No admin (None) means none."""
    if admin_id is None:
        return []
    cur.execute(
        f'SELECT {_COLUMNS} FROM {_table()} WHERE "user_id" = ? AND "enabled" = 1 AND "is_deleted" = 0 '
        f'ORDER BY "server_name"',
        (admin_id,),
    )
    return [ServerRow(*row) for row in cur.fetchall()]


def get_by_id(cur: dbapi.Cursor, server_id: int) -> tuple[ServerRow, bool] | None:
    """The server with this id and whether it is deleted, or None if no such id."""
    cur.execute(f'SELECT {_COLUMNS}, "is_deleted" FROM {_table()} WHERE "id" = ?', (server_id,))
    row = cur.fetchone()
    return None if row is None else (ServerRow(*row[:10]), bool(row[10]))


def soft_delete(cur: dbapi.Cursor, server_id: int, deleted_by: int) -> datetime | None:
    """Mark the server deleted (the row is kept). Returns the deletion time, or None if already deleted."""
    table = _table()
    cur.execute(
        f'UPDATE {table} SET "is_deleted" = 1, "deleted_by" = ?, "deleted_at" = CURRENT_TIMESTAMP '
        f'WHERE "id" = ? AND "is_deleted" = 0',
        (deleted_by, server_id),
    )
    if cur.rowcount == 0:
        return None
    cur.execute(f'SELECT "deleted_at" FROM {table} WHERE "id" = ?', (server_id,))
    return cur.fetchone()[0]


def live_ids(cur: dbapi.Cursor, server_ids: list[int], admin_id: int | None) -> set[int]:
    """Which of these ids are servers a user's key may be given: not deleted, enabled, and registered by
    admin_id (the admin who created the user). No admin (None) means none."""
    if not server_ids or admin_id is None:
        return set()
    placeholders = ", ".join("?" for _ in server_ids)
    cur.execute(
        f'SELECT "id" FROM {_table()} WHERE "id" IN ({placeholders}) AND "is_deleted" = 0 AND "enabled" = 1 '
        f'AND "user_id" = ?',
        (*server_ids, admin_id),
    )
    return {row[0] for row in cur.fetchall()}


def restore(cur: dbapi.Cursor, server_id: int) -> bool:
    """Undo a soft delete. False if the server isn't deleted. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "is_deleted" = 0, "deleted_by" = NULL, "deleted_at" = NULL '
        f'WHERE "id" = ? AND "is_deleted" = 1',
        (server_id,),
    )
    return cur.rowcount > 0


def find_by_name(cur: dbapi.Cursor, server_name: str, exclude_id: int | None = None) -> bool | None:
    """None if no server has this name (any case); otherwise whether that server is deleted.

    `exclude_id` skips one server, so renaming a server to (a different case of) its own name is allowed.
    """
    cur.execute(
        f'SELECT "is_deleted" FROM {_table()} WHERE LOWER("server_name") = LOWER(?) AND "id" <> ?',
        (server_name, -1 if exclude_id is None else exclude_id),
    )
    row = cur.fetchone()
    return None if row is None else bool(row[0])


# Columns an admin may edit. Only these names are ever put into the UPDATE statement.
EDITABLE = ("server_name", "server_url", "transport", "timeout_seconds", "enabled", "include_tools", "exclude_tools")


def update(cur: dbapi.Cursor, server_id: int, changes: dict[str, object]) -> bool:
    """Apply `changes` (column -> new value) to a live server. False if it is missing or deleted. The caller commits."""
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValueError(f"not editable: {sorted(unknown)}")
    assignments = ", ".join(f'"{column}" = ?' for column in changes)
    cur.execute(
        f'UPDATE {_table()} SET {assignments} WHERE "id" = ? AND "is_deleted" = 0',
        (*changes.values(), server_id),
    )
    return cur.rowcount > 0


def insert(
    cur: dbapi.Cursor,
    *,
    user_id: int,
    server_name: str,
    server_url: str,
    transport: str,
    timeout_seconds: int,
    enabled: bool,
) -> ServerRow:
    """Insert a server and return the saved row. The caller commits.

    include_tools and exclude_tools are left out, so the table defaults apply ('*' and NULL).
    """
    table = _table()
    cur.execute(
        f'INSERT INTO {table} ("user_id", "server_name", "server_url", "transport", "timeout_seconds", '
        f'"enabled", "is_deleted") VALUES (?, ?, ?, ?, ?, ?, 0)',
        (user_id, server_name, server_url, transport, timeout_seconds, int(enabled)),
    )
    cur.execute("SELECT CURRENT_IDENTITY_VALUE() FROM DUMMY")
    new_id = cur.fetchone()[0]
    cur.execute(f"SELECT {_COLUMNS} FROM {table} WHERE \"id\" = ?", (new_id,))
    return ServerRow(*cur.fetchone())
