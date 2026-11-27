"""Read the MCP servers to proxy from the server table (MCP_SERVER_TABLE).

Every row that isn't deleted (is_deleted = 0) is loaded, enabled or not: a disabled server stays connected so the
admin who registered it can still use it (see ApiKeyConfig.can_access); everyone else is kept away from it.
The gateway only reads; the backend registers, edits and deletes the rows.
"""

from __future__ import annotations

import logging

from hdbcli import dbapi
from pydantic import ValidationError

from mcp_gateway.config.settings import ALL_TOOLS, AuthConfig, DatabaseSettings, UpstreamConfig

logger = logging.getLogger(__name__)


def _split_tools(value: str | None) -> list[str]:
    """DB text ('add,multiply', '*' or NULL) -> list of full tool names."""
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def load_servers(
    cur: dbapi.Cursor, db: DatabaseSettings, auth_by_id: dict[int, AuthConfig] | None = None
) -> list[UpstreamConfig]:
    """The live servers. A row the gateway can't use is skipped with a warning instead of stopping every other
    server. auth_by_id (from load_server_auth) attaches each server's upstream auth config by its id."""
    auth_by_id = auth_by_id or {}
    cur.execute(
        f'SELECT "server_name", "server_url", "transport", "timeout_seconds", "include_tools", "exclude_tools", '
        f'"enabled", "user_id", "id" FROM {db.table(db.server_table)} WHERE "is_deleted" = 0 ORDER BY "id"'
    )
    servers: dict[str, UpstreamConfig] = {}
    for name, url, transport, timeout, include, exclude, enabled, owner_id, server_id in cur.fetchall():
        try:
            config = UpstreamConfig(
                name=name,
                url=url,
                transport=transport,
                enabled=bool(enabled),
                timeout_seconds=timeout,
                include_tools=_split_tools(include) or [ALL_TOOLS],  # the column's default is '*'
                exclude_tools=_split_tools(exclude),
                owner_id=owner_id,
                id=server_id,
                auth=auth_by_id.get(server_id),
            )
        except ValidationError as exc:
            logger.warning("Skipping server '%s' from the server table: %s", name, exc.errors()[0]["msg"])
            continue
        if config.name in servers:  # server_name is UNIQUE in the table, so this is only a safeguard
            logger.warning("Skipping duplicate server name '%s' in the server table", name)
            continue
        servers[config.name] = config
    return list(servers.values())
