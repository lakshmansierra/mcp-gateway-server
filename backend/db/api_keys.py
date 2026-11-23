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


def table() -> str:
    return _table()


class KeyListRow(NamedTuple):
    id: int
    user_id: int
    user_name: str
    owner_type: str  # admin / user
    key_name: str
    all_servers: int
    created_at: datetime
    is_deleted: int
    deleted_by: int | None
    deleted_at: datetime | None


class MappedServerRow(NamedTuple):
    key_id: int
    id: int
    server_name: str
    enabled: int
    is_deleted: int


def _managed_sql(where: str) -> str:
    """Keys owned by the admin or by users the admin created (parameters: admin id, admin id, then `where`'s)."""
    s = get_settings()
    users = s.table(s.user_table)
    return (
        f'SELECT k."id", k."user_id", u."user_name", u."type", k."key_name", k."all_servers", k."created_at", '
        f'k."is_deleted", k."deleted_by", k."deleted_at" '
        f'FROM {_table()} k JOIN {users} u ON u."id" = k."user_id" '
        f'WHERE (u."id" = ? OR (u."type" = \'user\' AND u."created_by" = ?)) AND {where}'
    )


def list_managed(cur: dbapi.Cursor, admin_id: int, user_id: int | None = None) -> list[KeyListRow]:
    """The admin's own keys and the keys of users they created, deleted ones included, newest first.
    `user_id` narrows it to one owner."""
    where, params = ("k.\"user_id\" = ?", (user_id,)) if user_id is not None else ("1 = 1", ())
    cur.execute(_managed_sql(where) + ' ORDER BY k."id" DESC', (admin_id, admin_id, *params))
    return [KeyListRow(*row) for row in cur.fetchall()]


def get_managed(cur: dbapi.Cursor, key_id: int, admin_id: int) -> KeyListRow | None:
    """This key if the admin manages it, deleted or not; else None."""
    cur.execute(_managed_sql('k."id" = ?'), (admin_id, admin_id, key_id))
    row = cur.fetchone()
    return None if row is None else KeyListRow(*row)


def list_own_live(cur: dbapi.Cursor, user_id: int) -> list[KeyRow]:
    """This account's keys that are not deleted, newest first."""
    cur.execute(
        f'SELECT "id", "user_id", "key_name", "all_servers", "created_at" FROM {_table()} '
        f'WHERE "user_id" = ? AND "is_deleted" = 0 ORDER BY "id" DESC',
        (user_id,),
    )
    return [KeyRow(*row) for row in cur.fetchall()]


def mapped_servers(cur: dbapi.Cursor, key_ids: list[int]) -> dict[int, list[MappedServerRow]]:
    """For each key, the servers in its mapping rows (deleted and disabled servers included), by server id."""
    out: dict[int, list[MappedServerRow]] = {key_id: [] for key_id in key_ids}
    if not key_ids:
        return out
    s = get_settings()
    placeholders = ", ".join("?" for _ in key_ids)
    cur.execute(
        f'SELECT m."key_id", s."id", s."server_name", s."enabled", s."is_deleted" '
        f'FROM {_mapping_table()} m JOIN {s.table(s.server_table)} s ON s."id" = m."mcp_id" '
        f'WHERE m."key_id" IN ({placeholders}) ORDER BY m."key_id", s."id"',
        tuple(key_ids),
    )
    for row in cur.fetchall():
        out[row[0]].append(MappedServerRow(*row))
    return out


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
