"""SQL for the client-to-gateway API key table and its key-to-server mapping table
(MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE and MCP_CLIENT_TO_GATEWAY_API_KEY_MAPPING_TABLE in .env)."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from hdbcli import dbapi

from backend.config import get_settings


class KeyRow(NamedTuple):
    id: int
    user_id: int
    key_name: str
    all_servers: int
    created_at: datetime


def _table() -> str:
    s = get_settings()
    return s.table(s.api_key_table)


def _mapping_table() -> str:
    s = get_settings()
    return s.table(s.api_key_mapping_table)


def find_by_name(cur: dbapi.Cursor, user_id: int, key_name: str) -> bool | None:
    """None if this user has no key with this name (any case); otherwise whether that key is deleted."""
    cur.execute(
        f'SELECT "is_deleted" FROM {_table()} WHERE "user_id" = ? AND LOWER("key_name") = LOWER(?)',
        (user_id, key_name),
    )
    row = cur.fetchone()
    return None if row is None else bool(row[0])


def insert(cur: dbapi.Cursor, *, user_id: int, key_name: str, key_hash: str, all_servers: bool) -> KeyRow:
    """Insert a key and return the saved row. The caller commits."""
    table = _table()
    cur.execute(
        f'INSERT INTO {table} ("user_id", "key_name", "key_hash", "all_servers", "is_deleted") VALUES (?, ?, ?, ?, 0)',
        (user_id, key_name, key_hash, int(all_servers)),
    )
    cur.execute("SELECT CURRENT_IDENTITY_VALUE() FROM DUMMY")
    new_id = cur.fetchone()[0]
    cur.execute(f'SELECT "id", "user_id", "key_name", "all_servers", "created_at" FROM {table} WHERE "id" = ?', (new_id,))
    return KeyRow(*cur.fetchone())


def map_servers(cur: dbapi.Cursor, key_id: int, server_ids: list[int]) -> None:
    """Give a key access to these servers (one mapping row each). The caller commits."""
    cur.executemany(
        f'INSERT INTO {_mapping_table()} ("key_id", "mcp_id") VALUES (?, ?)',
        [(key_id, server_id) for server_id in server_ids],
    )


def get_by_id(cur: dbapi.Cursor, key_id: int) -> tuple[KeyRow, bool] | None:
    """The key with this id and whether it is deleted, or None if no such id."""
    cur.execute(
        f'SELECT "id", "user_id", "key_name", "all_servers", "created_at", "is_deleted" FROM {_table()} WHERE "id" = ?',
        (key_id,),
    )
    row = cur.fetchone()
    return None if row is None else (KeyRow(*row[:5]), bool(row[5]))


def mapped_server_ids(cur: dbapi.Cursor, key_id: int) -> list[int]:
    cur.execute(f'SELECT "mcp_id" FROM {_mapping_table()} WHERE "key_id" = ? ORDER BY "mcp_id"', (key_id,))
    return [row[0] for row in cur.fetchall()]


def set_hash(cur: dbapi.Cursor, key_id: int, key_hash: str) -> bool:
    """Give a live key a new value (its hash). False if missing or deleted. The caller commits."""
    cur.execute(f'UPDATE {_table()} SET "key_hash" = ? WHERE "id" = ? AND "is_deleted" = 0', (key_hash, key_id))
    return cur.rowcount > 0


def unmap_servers(cur: dbapi.Cursor, key_id: int, server_ids: list[int]) -> None:
    """Take these servers away from a key (deletes their mapping rows). The caller commits."""
    if not server_ids:
        return
    placeholders = ", ".join("?" for _ in server_ids)
    cur.execute(
        f'DELETE FROM {_mapping_table()} WHERE "key_id" = ? AND "mcp_id" IN ({placeholders})',
        (key_id, *server_ids),
    )


def soft_delete(cur: dbapi.Cursor, key_id: int, deleted_by: int) -> datetime | None:
    """Mark the key deleted (the row and its mappings are kept). Returns the deletion time, or None if already deleted."""
    table = _table()
    cur.execute(
        f'UPDATE {table} SET "is_deleted" = 1, "deleted_by" = ?, "deleted_at" = CURRENT_TIMESTAMP '
        f'WHERE "id" = ? AND "is_deleted" = 0',
        (deleted_by, key_id),
    )
    if cur.rowcount == 0:
        return None
    cur.execute(f'SELECT "deleted_at" FROM {table} WHERE "id" = ?', (key_id,))
    return cur.fetchone()[0]


def restore(cur: dbapi.Cursor, key_id: int) -> bool:
    """Undo a soft delete. False if the key isn't deleted. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "is_deleted" = 0, "deleted_by" = NULL, "deleted_at" = NULL '
        f'WHERE "id" = ? AND "is_deleted" = 1',
        (key_id,),
    )
    return cur.rowcount > 0


def soft_delete_for_user(cur: dbapi.Cursor, user_id: int, deleted_by: int) -> int:
    """Revoke all of a user's live keys. Returns how many were revoked. The caller commits."""
    cur.execute(
        f'UPDATE {_table()} SET "is_deleted" = 1, "deleted_by" = ?, "deleted_at" = CURRENT_TIMESTAMP '
        f'WHERE "user_id" = ? AND "is_deleted" = 0',
        (deleted_by, user_id),
    )
    return cur.rowcount
