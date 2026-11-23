"""Tools of your MCP servers (logged-in admin only; read-only: the gateway records them).

GET /api/admin/tools                     every tool of your servers (?server_id= for one server). Tools a server
                                         no longer lists are included, tagged is_removed; `hidden` means the
                                         server's include_tools / exclude_tools keep the tool from clients.
GET /api/admin/tools/{tool_id}           one tool
GET /api/admin/tools/{tool_id}/changes   its history, newest first: added / removed / changed (description or
                                         input schema), with the values before and after
A tool shows up once the gateway has connected to its server. Tools of other admins' servers answer 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from hdbcli import dbapi

from backend.auth import current_admin
from backend.db import get_db
from backend.models import ToolChangeOut, ToolOut, UserOut
from backend.services import admin_views

router = APIRouter(prefix="/api/admin/tools", tags=["tools"])


@router.get("", response_model=list[ToolOut])
def list_tools(
    server_id: int | None = Query(None, gt=0, description="Only this server's tools"),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> list[ToolOut]:
    return admin_views.list_tools(conn, admin, server_id)


@router.get("/{tool_id}", response_model=ToolOut)
def get_tool(
    tool_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ToolOut:
    return admin_views.get_tool(conn, tool_id, admin)


@router.get("/{tool_id}/changes", response_model=list[ToolChangeOut])
def tool_changes(
    tool_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> list[ToolChangeOut]:
    return admin_views.tool_changes(conn, tool_id, admin)
