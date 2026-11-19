"""Connection to SAP HANA, where the backend keeps the MCP servers and client API keys."""

from __future__ import annotations

from hdbcli import dbapi

from mcp_gateway.config.settings import DatabaseSettings


def connect(db: DatabaseSettings) -> dbapi.Connection:
    return dbapi.connect(
        address=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        encrypt=True,  # HANA Cloud only accepts TLS connections
        sslValidateCertificate=True,
        # HANA_CONNECT_TIMEOUT / HANA_QUERY_TIMEOUT are seconds; hdbcli takes milliseconds.
        connectTimeout=int(db.connect_timeout * 1000),
        communicationTimeout=int(db.query_timeout * 1000),
    )
