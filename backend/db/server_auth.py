"""SQL for the per-server upstream auth table (MCP_SERVER_AUTH_TABLE).

One row per server that needs auth, keyed by mcp_id (UNIQUE). The backend writes these; the gateway reads them
to build the Authorization header it sends to the upstream. Secrets (token / password / client_secret) are stored
reversibly because the gateway must present them, but no API response ever returns them.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from hdbcli import dbapi

from backend.config import get_settings

# The config columns, in a fixed order. mcp_id, created_at and updated_at are handled separately.
_CONFIG_COLUMNS = (
    "auth_type",
    "token",
    "username",
    "password",
    "oauth_grant_type",
    "add_auth_data_to",
    "header_prefix",
    "token_url",
    "client_id",
    "client_secret",
    "scope",
    "client_authentication",
)


class AuthRow(NamedTuple):
    mcp_id: int
    auth_type: str
    token: str | None
    username: str | None
    password: str | None
    oauth_grant_type: str | None
    add_auth_data_to: str | None
    header_prefix: str | None
    token_url: str | None
    client_id: str | None
    client_secret: str | None
    scope: str | None
    client_authentication: str | None


def _table() -> str:
    s = get_settings()
    return s.table(s.server_auth_table)


def table() -> str:
    return _table()


_SELECT_COLUMNS = ", ".join('"' + c + '"' for c in ("mcp_id", *_CONFIG_COLUMNS))


def get(cur: dbapi.Cursor, mcp_id: int) -> AuthRow | None:
    """The auth config for one server, or None if it has none."""
    cur.execute(f'SELECT {_SELECT_COLUMNS} FROM {_table()} WHERE "mcp_id" = ?', (mcp_id,))
    row = cur.fetchone()
    return None if row is None else AuthRow(*row)


def by_server_ids(cur: dbapi.Cursor, server_ids: list[int]) -> dict[int, AuthRow]:
    """Auth configs for many servers at once (for list views), keyed by server id."""
    if not server_ids:
        return {}
    placeholders = ", ".join("?" for _ in server_ids)
    cur.execute(
        f'SELECT {_SELECT_COLUMNS} FROM {_table()} WHERE "mcp_id" IN ({placeholders})', tuple(server_ids)
    )
    return {row[0]: AuthRow(*row) for row in cur.fetchall()}


def upsert(cur: dbapi.Cursor, mcp_id: int, columns: dict[str, object]) -> None:
    """Store a full auth config for the server (replacing any existing one). The caller commits.

    `columns` must hold exactly the config columns (from AuthIn.columns()). This is a full replace, not a merge:
    every secret the type needs is expected to be present.
    """
    missing = set(_CONFIG_COLUMNS) - set(columns)
    if missing:
        raise ValueError(f"auth columns missing: {sorted(missing)}")
    values = tuple(columns[c] for c in _CONFIG_COLUMNS)
    table = _table()
    if get(cur, mcp_id) is not None:
        assignments = ", ".join(f'"{c}" = ?' for c in _CONFIG_COLUMNS)
        cur.execute(
            f'UPDATE {table} SET {assignments}, "updated_at" = CURRENT_TIMESTAMP WHERE "mcp_id" = ?',
            (*values, mcp_id),
        )
    else:
        collist = ", ".join(f'"{c}"' for c in ("mcp_id", *_CONFIG_COLUMNS))
        placeholders = ", ".join("?" for _ in range(len(_CONFIG_COLUMNS) + 1))
        cur.execute(f'INSERT INTO {table} ({collist}) VALUES ({placeholders})', (mcp_id, *values))


def delete(cur: dbapi.Cursor, mcp_id: int) -> None:
    """Remove a server's auth config (auth_type 'none'). No error if there was none. The caller commits."""
    cur.execute(f'DELETE FROM {_table()} WHERE "mcp_id" = ?', (mcp_id,))
