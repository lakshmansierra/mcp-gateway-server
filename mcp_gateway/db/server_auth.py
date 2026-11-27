"""Read per-server upstream auth configs from the auth table (MCP_SERVER_AUTH_TABLE).

One row per server that needs authentication, keyed by mcp_id (the server's id in the server table). Servers
without a row use no auth. The gateway only reads; the backend writes these rows. Secrets are stored reversibly
(the gateway must present them to the upstream) and never logged.

A row the gateway can't use is skipped with a warning instead of stopping every other server's auth.
"""

from __future__ import annotations

import logging

from hdbcli import dbapi
from pydantic import ValidationError

from mcp_gateway.config.settings import AuthConfig, DatabaseSettings

logger = logging.getLogger(__name__)

# Column order of the SELECT below. "mcp_id" identifies the server; the rest map onto AuthConfig fields.
_COLUMNS = (
    "mcp_id",
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


def load_server_auth(cur: dbapi.Cursor, db: DatabaseSettings) -> dict[int, AuthConfig]:
    """Auth config per server id. Raises dbapi.Error if HANA can't be reached or the table is missing."""
    columns = ", ".join(f'"{c}"' for c in _COLUMNS)
    cur.execute(f"SELECT {columns} FROM {db.table(db.server_auth_table)}")
    out: dict[int, AuthConfig] = {}
    for row in cur.fetchall():
        fields = dict(zip(_COLUMNS, row))
        mcp_id = fields.pop("mcp_id")
        try:
            out[int(mcp_id)] = AuthConfig(**fields)
        except ValidationError as exc:
            logger.warning("Ignoring auth config for server id %s: %s", mcp_id, exc.errors()[0]["msg"])
    return out
