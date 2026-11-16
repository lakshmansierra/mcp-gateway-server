"""Database layer: the HANA connection and the SQL for each table."""

from backend.db.connection import connect, get_db

__all__ = ["connect", "get_db"]
