"""The logged-in account itself (admins and users).

PATCH /api/me/password  change your own password (old password required)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from hdbcli import dbapi

from backend.auth import current_user
from backend.db import get_db
from backend.models import PasswordChange, UserOut
from backend.services import users as user_service

router = APIRouter(prefix="/api/me", tags=["me"])


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    me: UserOut = Depends(current_user),
    conn: dbapi.Connection = Depends(get_db),
) -> Response:
    user_service.change_own_password(conn, me, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
