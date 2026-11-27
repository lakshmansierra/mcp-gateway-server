"""Gateway-written cache of OAuth2 access tokens (MCP_SERVER_TOKEN_CACHE_TABLE), one row per oauth2 server.

The gateway fetches a short-lived access token from an upstream's token endpoint and stores it here with its
expiry, so it isn't refetched on every reconnect (and survives a gateway restart). Only OAuth2 servers use it;
bearer/basic send a static header. This is the only gateway-owned write outside the usage tables.
"""

from __future__ import annotations

from datetime import datetime

from hdbcli import dbapi

from mcp_gateway.config.settings import DatabaseSettings


def read(cur: dbapi.Cursor, db: DatabaseSettings, mcp_id: int) -> tuple[str | None, datetime | None] | None:
    """The cached (access_token, expires_at) for a server, or None if nothing is cached."""
    cur.execute(
        f'SELECT "access_token", "access_token_expires_at" FROM {db.table(db.token_cache_table)} WHERE "mcp_id" = ?',
        (mcp_id,),
    )
    row = cur.fetchone()
    return None if row is None else (row[0], row[1])


def write(cur: dbapi.Cursor, db: DatabaseSettings, mcp_id: int, access_token: str, expires_at: datetime) -> None:
    """Store (replace) the cached token for a server. The caller commits."""
    table = db.table(db.token_cache_table)
    cur.execute(f'DELETE FROM {table} WHERE "mcp_id" = ?', (mcp_id,))
    cur.execute(
        f'INSERT INTO {table} ("mcp_id", "access_token", "access_token_expires_at", "updated_at") '
        f"VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        (mcp_id, access_token, expires_at),
    )
