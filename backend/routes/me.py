"""The logged-in account itself (admins and users).

GET   /api/me             who you are (the logged-in admin or user)
PATCH /api/me/password    change your own password (old password required); logs you out on every device
POST  /api/me/logout      log out on this device only (other devices stay logged in)
POST  /api/me/logout-all  log out on every device (e.g. a device was lost)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from hdbcli import dbapi

from backend.auth import Session, current_session, current_user
from backend.db import get_db
from backend.models import PasswordChange, UserOut
from backend.services import users as user_service

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=UserOut)
def who_am_i(me: UserOut = Depends(current_user)) -> UserOut:
    return me


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    me: UserOut = Depends(current_user),
    conn: dbapi.Connection = Depends(get_db),
) -> Response:
    user_service.change_own_password(conn, me, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: Session = Depends(current_session), conn: dbapi.Connection = Depends(get_db)) -> Response:
    user_service.logout_this_device(conn, session.user.id, session.jti, session.expires_at)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(me: UserOut = Depends(current_user), conn: dbapi.Connection = Depends(get_db)) -> Response:
    user_service.logout_everywhere(conn, me)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
