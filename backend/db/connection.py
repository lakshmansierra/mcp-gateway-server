"""SAP HANA connection: one connection per request, closed when the request ends."""

from __future__ import annotations

from collections.abc import Iterator

from hdbcli import dbapi

from backend.config import get_settings


def connect() -> dbapi.Connection:
    s = get_settings()
    return dbapi.connect(
        address=s.hana_host,
        port=s.hana_port,
        user=s.hana_user,
        password=s.hana_password,
        encrypt=True,  # HANA Cloud only accepts TLS connections
        sslValidateCertificate=True,
    )


def get_db() -> Iterator[dbapi.Connection]:
    """FastAPI dependency: `conn: dbapi.Connection = Depends(get_db)`."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
