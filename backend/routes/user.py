"""User accounts.

POST /api/user/login        checks the password and returns a login token (users only; admins use /api/admin/login)

The rest is for logged-in users only (admins get 403) and never shows anything deleted or removed:
GET  /api/user/servers      the servers you may use: added by your admin, enabled, not deleted
GET  /api/user/servers/{server_id}/tools
                            the tools you can call on one of them (404 for any other server id)
GET  /api/user/tools        the tools you can call on all of them (?server_id= for one)
GET  /api/user/keys         your live API keys and the servers each reaches (a disabled server shows enabled = false)
GET  /api/user/usage        your own calls, counted in total, per server, per tool and per key
GET  /api/user/usage/calls  your own call log, newest first, one page at a time (limit / offset)
Both usage routes take start / end (UTC), server_id, tool_id, key_id and status.

Users can't sign up themselves: an admin creates them with POST /api/admin/users.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query
from hdbcli import dbapi

from backend.auth import current_plain_user
from backend.db import get_db
from backend.db.usage import CallFilter
from backend.models import (
    CallPageOut,
    CallStatus,
    LoginRequest,
    MyUsageSummaryOut,
    TokenOut,
    UserKeyOut,
    UserOut,
    UserServerOut,
    UserToolOut,
)
from backend.routes.usage import make_filter
from backend.services import accounts, user_views

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/login", response_model=TokenOut)
def login_user(body: LoginRequest, conn: dbapi.Connection = Depends(get_db)) -> TokenOut:
    return accounts.login(conn, body, "user")


@router.get("/servers", response_model=list[UserServerOut])
def my_servers(me: UserOut = Depends(current_plain_user), conn: dbapi.Connection = Depends(get_db)) -> list[UserServerOut]:
    return user_views.list_servers(conn, me)


@router.get("/servers/{server_id}/tools", response_model=list[UserToolOut])
def my_server_tools(
    server_id: int = Path(gt=0),
    me: UserOut = Depends(current_plain_user),
    conn: dbapi.Connection = Depends(get_db),
) -> list[UserToolOut]:
    return user_views.list_tools(conn, me, server_id)


@router.get("/tools", response_model=list[UserToolOut])
def my_tools(
    server_id: int | None = Query(None, gt=0, description="Only this server's tools"),
    me: UserOut = Depends(current_plain_user),
    conn: dbapi.Connection = Depends(get_db),
) -> list[UserToolOut]:
    return user_views.list_tools(conn, me, server_id)


@router.get("/keys", response_model=list[UserKeyOut])
def my_keys(me: UserOut = Depends(current_plain_user), conn: dbapi.Connection = Depends(get_db)) -> list[UserKeyOut]:
    return user_views.list_keys(conn, me)


def my_call_filter(
    start: datetime | None = Query(None, description="Calls at or after this time, e.g. 2026-11-01T00:00:00 (UTC)"),
    end: datetime | None = Query(None, description="Calls before this time (UTC)"),
    server_id: int | None = Query(None, gt=0),
    tool_id: int | None = Query(None, gt=0),
    key_id: int | None = Query(None, gt=0, description="Calls made with this one of your keys"),
    status_: CallStatus | None = Query(None, alias="status"),
) -> CallFilter:
    return make_filter(start, end, server_id=server_id, tool_id=tool_id, key_id=key_id, status=status_)


@router.get("/usage", response_model=MyUsageSummaryOut)
def my_usage(
    f: CallFilter = Depends(my_call_filter),
    me: UserOut = Depends(current_plain_user),
    conn: dbapi.Connection = Depends(get_db),
) -> MyUsageSummaryOut:
    return user_views.usage_summary(conn, me, f)


@router.get("/usage/calls", response_model=CallPageOut)
def my_calls(
    f: CallFilter = Depends(my_call_filter),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    me: UserOut = Depends(current_plain_user),
    conn: dbapi.Connection = Depends(get_db),
) -> CallPageOut:
    return user_views.call_log(conn, me, f, limit, offset)
