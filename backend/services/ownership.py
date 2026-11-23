"""Which admin may manage what.

An admin manages the things they own, and the things owned by the users they created (users.created_by).
Used for servers and API keys; user accounts have their own rules in services/users.py.

Something another admin manages answers 404, exactly like an id that doesn't exist, so an admin can't find out
which ids belong to other admins.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import users
from backend.models import UserOut


def admin_manages(cur: dbapi.Cursor, owner_id: int, admin: UserOut) -> bool:
    if owner_id == admin.id:
        return True
    found = users.get_by_id(cur, owner_id)
    if found is None:
        return False
    owner, _ = found
    return owner.type == "user" and owner.created_by == admin.id


def require_admin_manages(cur: dbapi.Cursor, owner_id: int, admin: UserOut, not_found: str) -> None:
    """`not_found` is the 404 message, the same one a missing id gets, e.g. "Server 5 not found"."""
    if not admin_manages(cur, owner_id, admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
