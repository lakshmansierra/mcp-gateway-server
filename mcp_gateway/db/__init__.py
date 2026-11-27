"""SAP HANA access: the MCP servers and client API keys come from the backend's tables (read-only)."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_gateway.config.settings import ApiKeyConfig, DatabaseSettings, UpstreamConfig
from mcp_gateway.db.api_keys import load_api_keys
from mcp_gateway.db.connection import connect
from mcp_gateway.db.server_auth import load_server_auth
from mcp_gateway.db.servers import load_servers


@dataclass(frozen=True)
class Registry:
    """Everything the gateway reads from HANA, as of one read."""

    servers: list[UpstreamConfig]
    api_keys: list[ApiKeyConfig]


def load_registry(db: DatabaseSettings) -> Registry:
    """Read the live servers and API keys over one connection. Raises hdbcli's dbapi.Error if HANA can't be
    reached or a table is missing."""
    conn = connect(db)
    try:
        cur = conn.cursor()
        try:
            auth_by_id = load_server_auth(cur, db)
            return Registry(servers=load_servers(cur, db, auth_by_id), api_keys=load_api_keys(cur, db))
        finally:
            cur.close()
    finally:
        conn.close()
