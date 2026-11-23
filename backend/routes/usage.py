"""Tool usage of your MCP servers (logged-in admin only; read-only: the gateway records every tools/call).

GET /api/admin/usage        call counts (ok / error / timeout, average duration, last call) in total, per server,
                            per tool (every tool, called or not) and per account
GET /api/admin/usage/calls  the call log, newest first, one page at a time (limit / offset)

Both take the same optional filters: start / end (called_at >= start and < end; times without a zone are UTC),
server_id, tool_id, user_id, key_id, status. Only calls to tools of your servers are counted.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from hdbcli import dbapi

from backend.auth import current_admin
from backend.db import get_db
from backend.db.usage import CallFilter
from backend.models import CallPageOut, CallStatus, UsageSummaryOut, UserOut
from backend.services import admin_views

router = APIRouter(prefix="/api/admin/usage", tags=["usage"])


def make_filter(start: datetime | None, end: datetime | None, **ids: object) -> CallFilter:
    start, end = admin_views.utc_naive(start), admin_views.utc_naive(end)
    if start and end and start >= end:
        raise HTTPException(422, "start must be before end")
    return CallFilter(start=start, end=end, **ids)


def call_filter(
    start: datetime | None = Query(None, description="Calls at or after this time, e.g. 2026-11-01T00:00:00 (UTC)"),
    end: datetime | None = Query(None, description="Calls before this time (UTC)"),
    server_id: int | None = Query(None, gt=0),
    tool_id: int | None = Query(None, gt=0),
    user_id: int | None = Query(None, gt=0, description="Calls made by this account (its keys)"),
    key_id: int | None = Query(None, gt=0),
    status_: CallStatus | None = Query(None, alias="status"),
) -> CallFilter:
    return make_filter(start, end, server_id=server_id, tool_id=tool_id, user_id=user_id, key_id=key_id, status=status_)


@router.get("", response_model=UsageSummaryOut)
def usage_summary(
    f: CallFilter = Depends(call_filter),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> UsageSummaryOut:
    return admin_views.usage_summary(conn, admin, f)


@router.get("/calls", response_model=CallPageOut)
def call_log(
    f: CallFilter = Depends(call_filter),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> CallPageOut:
    return admin_views.call_log(conn, admin, f, limit, offset)
