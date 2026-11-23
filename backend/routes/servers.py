"""MCP servers (logged-in admin only).

GET    /api/admin/servers              your servers, deleted and disabled ones included (tagged is_deleted)
GET    /api/admin/servers/{server_id}  one of your servers
GET    /api/admin/servers/{server_id}/tools
                                       the tools that server lists, or once listed (tagged is_removed)
POST   /api/admin/servers              register an MCP server
PATCH  /api/admin/servers/{server_id}  edit a server (only the fields sent; not if deleted)
DELETE /api/admin/servers/{server_id}  soft-delete an MCP server
POST   /api/admin/servers/{server_id}/restore
                                       undo a soft delete
All of them: only servers you added, or that users you created added; any other id answers 404.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from hdbcli import dbapi

from backend.auth import current_admin
from backend.db import get_db
from backend.models import ServerCreate, ServerDeletedOut, ServerListOut, ServerOut, ServerUpdate, ToolOut, UserOut
from backend.services import admin_views
from backend.services import servers as server_service

router = APIRouter(prefix="/api/admin/servers", tags=["servers"])


@router.get("", response_model=list[ServerListOut])
def list_servers(admin: UserOut = Depends(current_admin), conn: dbapi.Connection = Depends(get_db)) -> list[ServerListOut]:
    return admin_views.list_servers(conn, admin)


@router.get("/{server_id}", response_model=ServerListOut)
def get_server(
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerListOut:
    return admin_views.get_server(conn, server_id, admin)


@router.get("/{server_id}/tools", response_model=list[ToolOut])
def list_server_tools(
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> list[ToolOut]:
    return admin_views.list_tools(conn, admin, server_id)


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
def register_server(
    body: ServerCreate,
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerOut:
    return server_service.register_server(conn, body, admin)


@router.patch("/{server_id}", response_model=ServerOut)
def update_server(
    body: ServerUpdate,
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerOut:
    return server_service.update_server(conn, server_id, body, admin)


@router.delete("/{server_id}", response_model=ServerDeletedOut)
def delete_server(
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerDeletedOut:
    return server_service.delete_server(conn, server_id, admin)


@router.post("/{server_id}/restore", response_model=ServerOut)
def restore_server(
    server_id: int = Path(gt=0),
    admin: UserOut = Depends(current_admin),
    conn: dbapi.Connection = Depends(get_db),
) -> ServerOut:
    return server_service.restore_server(conn, server_id, admin)
