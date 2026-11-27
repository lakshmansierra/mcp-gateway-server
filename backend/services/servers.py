"""Registering MCP servers (admin actions)."""

from __future__ import annotations

from fastapi import HTTPException, status
from hdbcli import dbapi

from backend.db import server_auth, servers
from backend.models import AuthIn, AuthStatusOut, ServerCreate, ServerDeletedOut, ServerOut, ServerUpdate, UserOut
from backend.models.server import split_tools
from backend.services.ownership import require_admin_manages


def apply_auth(cur: dbapi.Cursor, mcp_id: int, auth: AuthIn | None) -> None:
    """Store, replace or remove a server's auth config. None (field not sent) leaves it unchanged; auth_type
    'none' removes it; any other type writes a full replacement. The caller commits."""
    if auth is None:
        return
    if auth.auth_type == "none":
        server_auth.delete(cur, mcp_id)
    else:
        server_auth.upsert(cur, mcp_id, auth.columns())


def auth_status(row: server_auth.AuthRow | None) -> AuthStatusOut:
    """The non-secret view of an auth config for GET responses (never the secrets themselves)."""
    if row is None:
        return AuthStatusOut()
    return AuthStatusOut(
        auth_type=row.auth_type,
        header_prefix=row.header_prefix,
        username=row.username,
        oauth_grant_type=row.oauth_grant_type,
        add_auth_data_to=row.add_auth_data_to,
        token_url=row.token_url,
        client_id=row.client_id,
        scope=row.scope,
        client_authentication=row.client_authentication,
        has_token=bool(row.token),
        has_password=bool(row.password),
        has_client_secret=bool(row.client_secret),
    )


def to_out(row: servers.ServerRow) -> ServerOut:
    return ServerOut(
        id=row.id,
        user_id=row.user_id,
        server_name=row.server_name,
        server_url=row.server_url,
        transport=row.transport,
        timeout_seconds=row.timeout_seconds,
        enabled=bool(row.enabled),
        include_tools=split_tools(row.include_tools),
        exclude_tools=split_tools(row.exclude_tools),
        created_at=row.created_at,
    )


def register_server(conn: dbapi.Connection, body: ServerCreate, admin: UserOut) -> ServerOut:
    cur = conn.cursor()
    try:
        # server_name is UNIQUE in the table, deleted servers included. The lookup ignores case, so "ABC" and
        # "abc" can't both exist (they would be confusing as tool prefixes).
        deleted = servers.find_by_name(cur, body.server_name)
        if deleted is not None:
            detail = "belongs to a deleted server" if deleted else "already exists"
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{body.server_name}' {detail}")

        row = servers.insert(
            cur,
            user_id=admin.id,
            server_name=body.server_name,
            server_url=str(body.server_url),
            transport=body.transport,
            timeout_seconds=body.timeout_seconds,
            enabled=body.enabled,
        )
        apply_auth(cur, row.id, body.auth)
        conn.commit()
    except HTTPException:
        raise
    except dbapi.IntegrityError as exc:
        # Registered by another request at the same moment: the UNIQUE constraint stopped this one.
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{body.server_name}' already exists") from exc
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return to_out(row)


def update_server(conn: dbapi.Connection, server_id: int, body: ServerUpdate, admin: UserOut) -> ServerOut:
    """Change the fields that were sent. Deleted servers can't be edited. Same ownership rule as deleting:
    servers the admin added, or that users the admin created added.

    Renaming a server changes its tool prefix (abc__add -> new__add); key mappings use the server id, so
    they keep working.
    """
    changes = body.changes()
    cur = conn.cursor()
    try:
        found = servers.get_by_id(cur, server_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Server {server_id} not found")
        current, is_deleted = found
        require_admin_manages(cur, current.user_id, admin, f"Server {server_id} not found")
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{current.server_name}' is deleted and can't be edited")

        new_name = changes.get("server_name")
        if new_name is not None:
            taken = servers.find_by_name(cur, new_name, exclude_id=server_id)
            if taken is not None:
                detail = "belongs to a deleted server" if taken else "already exists"
                raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{new_name}' {detail}")

        # changes may be empty when only auth was sent; in that case skip the server-row UPDATE.
        if changes and not servers.update(cur, server_id, changes):  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{current.server_name}' is deleted and can't be edited")
        apply_auth(cur, server_id, body.auth)
        row, _ = servers.get_by_id(cur, server_id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.IntegrityError as exc:
        # Another request took the new name at the same moment: the UNIQUE constraint stopped this one.
        conn.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Server name '{changes.get('server_name')}' already exists") from exc
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return to_out(row)


def restore_server(conn: dbapi.Connection, server_id: int, admin: UserOut) -> ServerOut:
    """Undo a server's soft delete. It comes back with its old settings (including enabled/disabled),
    and keys that were mapped to it can use it again. Same ownership rule as deleting."""
    cur = conn.cursor()
    try:
        found = servers.get_by_id(cur, server_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Server {server_id} not found")
        row, is_deleted = found
        require_admin_manages(cur, row.user_id, admin, f"Server {server_id} not found")
        if not is_deleted or not servers.restore(cur, server_id):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{row.server_name}' is not deleted")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return to_out(row)


def delete_server(conn: dbapi.Connection, server_id: int, admin: UserOut) -> ServerDeletedOut:
    """Soft-delete a server: the row stays (is_deleted = 1, deleted_by = the admin, deleted_at = now).

    An admin may delete the servers they added and the servers added by users they created.

    Its name stays taken. Rows in the key-to-server mapping table are kept as history; anything reading
    servers for the gateway must skip deleted ones.
    """
    cur = conn.cursor()
    try:
        found = servers.get_by_id(cur, server_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Server {server_id} not found")
        row, is_deleted = found
        require_admin_manages(cur, row.user_id, admin, f"Server {server_id} not found")
        if is_deleted:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{row.server_name}' is already deleted")

        deleted_at = servers.soft_delete(cur, server_id, admin.id)
        if deleted_at is None:  # deleted by another request in the meantime
            raise HTTPException(status.HTTP_409_CONFLICT, f"Server '{row.server_name}' is already deleted")
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except dbapi.Error as exc:
        conn.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Database error: {exc.errortext}") from exc
    finally:
        cur.close()

    return ServerDeletedOut(server=to_out(row), deleted_by=admin.id, deleted_at=deleted_at)
