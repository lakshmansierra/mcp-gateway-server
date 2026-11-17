"""Connection to SAP HANA, where the backend keeps the MCP servers and client API keys."""

from __future__ import annotations

from hdbcli import dbapi

from mcp_gateway.config.settings import DatabaseSettings

# Milliseconds. Without these a dead network can block a read forever, and the gateway would stop re-reading
# servers and keys (deleted keys would keep working). With them a stuck read fails and the next round retries.
CONNECT_TIMEOUT_MS = 10_000
COMMUNICATION_TIMEOUT_MS = 30_000


def connect(db: DatabaseSettings) -> dbapi.Connection:
    return dbapi.connect(
        address=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        encrypt=True,  # HANA Cloud only accepts TLS connections
        sslValidateCertificate=True,
        connectTimeout=CONNECT_TIMEOUT_MS,
        communicationTimeout=COMMUNICATION_TIMEOUT_MS,
    )
