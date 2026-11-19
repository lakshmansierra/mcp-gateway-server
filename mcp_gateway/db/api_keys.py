"""Read the client API keys from the key table (MCP_CLIENT_TO_GATEWAY_API_KEY_TABLE).

A key is live when it isn't deleted and neither is the user who owns it. Its servers:
  all_servers = 1 (admins' keys)  every server that admin registered (the server row's user_id), enabled or not
  all_servers = 0 (users' keys)   the servers picked for it, from the mapping table, while they are enabled,
                                  and only those registered by the admin who created the user (created_by);
                                  deleted servers drop out
Only the SHA-256 hash of each key is stored, so the gateway hashes what a client sends and looks it up.
"""

from __future__ import annotations

from hdbcli import dbapi

from mcp_gateway.config.settings import ApiKeyConfig, DatabaseSettings


def load_api_keys(cur: dbapi.Cursor, db: DatabaseSettings) -> list[ApiKeyConfig]:
    keys_t, map_t = db.table(db.api_key_table), db.table(db.api_key_mapping_table)
    users_t, servers_t = db.table(db.user_table), db.table(db.server_table)

    cur.execute(
        f'SELECT k."id", k."user_id", u."created_by", u."user_name", k."key_name", k."key_hash", k."all_servers" '
        f'FROM {keys_t} k JOIN {users_t} u ON u."id" = k."user_id" '
        f'WHERE k."is_deleted" = 0 AND u."is_deleted" = 0 ORDER BY k."id"'
    )
    rows = cur.fetchall()

    cur.execute(
        f'SELECT m."key_id", s."server_name" FROM {map_t} m JOIN {servers_t} s ON s."id" = m."mcp_id" '
        f'WHERE s."is_deleted" = 0'
    )
    servers_of: dict[int, set[str]] = {}
    for key_id, server_name in cur.fetchall():
        servers_of.setdefault(key_id, set()).add(server_name)

    return [
        ApiKeyConfig(
            id=key_id,
            user_id=user_id,
            admin_id=user_id if all_servers else created_by,  # whose servers this key may reach
            name=f"{user_name}/{key_name}",
            key_hash=key_hash,
            all_servers=bool(all_servers),
            servers=frozenset(() if all_servers else servers_of.get(key_id, ())),
        )
        for key_id, user_id, created_by, user_name, key_name, key_hash, all_servers in rows
    ]
