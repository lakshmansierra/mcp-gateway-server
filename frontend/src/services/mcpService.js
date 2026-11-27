/**
 * MCP Gateway backend API: one function per endpoint in the backend's OpenAPI (Swagger) docs.
 *
 * Request bodies match the backend schemas exactly (LoginRequest, ServerCreate, ServerUpdate, KeyCreate,
 * KeyServersUpdate, RegisterRequest, PasswordChange, PasswordReset). Lists come straight from the backend:
 * admins see their own and their users' rows (deleted ones tagged is_deleted), users see only what they can use.
 *
 * POST /api/admin/register is intentionally not wrapped here.
 */

import { request } from './api.js';

/* ---------- Constants ---------- */

/** ServerCreate.transport enum */
export const TRANSPORTS = {
  streamable_http: 'Streamable HTTP',
  sse: 'SSE',
};

/** Shared pattern of RegisterRequest.user_name and KeyCreate.key_name */
export const NAME_PATTERN = /^[A-Za-z0-9._-]+$/;
/** ServerCreate.server_name */
export const SERVER_NAME_PATTERN = /^[A-Za-z0-9_-]+$/;
export const MIN_PASSWORD = 8;

/** tools/call outcomes recorded by the gateway */
export const CALL_STATUSES = ['ok', 'error', 'timeout'];

/** How the gateway authenticates to an upstream (AuthIn.auth_type). */
export const AUTH_TYPES = { none: 'No auth', basic: 'Basic', bearer: 'Bearer', oauth2: 'OAuth 2.0' };
/** OAuth2 grant types the gateway can run headless (AuthIn.oauth_grant_type). */
export const OAUTH_GRANTS = { client_credentials: 'Client Credentials', password: 'Password Credentials' };
/** How client credentials are sent to the token endpoint (AuthIn.client_authentication). */
export const CLIENT_AUTH = { basic_header: 'Send as Basic Auth header', body: 'Send client credentials in body' };
/** Where the authorization is added (AuthIn.add_auth_data_to). */
export const ADD_AUTH_TO = { header: 'Request Headers', url: 'Request URL' };

/** The gateway's single MCP endpoint; API keys decide which servers a client reaches. */
export const GATEWAY_MCP_URL = (import.meta.env.VITE_GATEWAY_MCP_URL || '').replace(/\/+$/, '');

/** {a: 1, b: null} -> "?a=1" (empty values are left out) */
function query(params = {}) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : '';
}

/* ---------- Health ---------- */

/** GET /api/health -> { status, database } */
export const checkHealth = () => request('GET', '/api/health', { auth: false });

/* ---------- Accounts ---------- */

/**
 * POST /api/admin/login or POST /api/user/login with LoginRequest { user_name, password }
 * @returns TokenOut { access_token, token_type, expires_in, user }
 */
export function login(kind, user_name, password) {
  const path = kind === 'admin' ? '/api/admin/login' : '/api/user/login';
  return request('POST', path, { body: { user_name, password }, auth: false });
}

/** GET /api/me -> UserOut: the logged-in account */
export const getMe = () => request('GET', '/api/me');

/** POST /api/me/logout: ends this device's session only. */
export const logout = () => request('POST', '/api/me/logout');

/** POST /api/me/logout-all: ends the session on every device. */
export const logoutAll = () => request('POST', '/api/me/logout-all');

/** PATCH /api/me/password with PasswordChange { old_password, new_password }; logs out everywhere. */
export const changePassword = (old_password, new_password) =>
  request('PATCH', '/api/me/password', { body: { old_password, new_password } });

/* ---------- MCP servers (admin) ---------- */

/** GET /api/admin/servers -> ServerListOut[]: deleted and disabled ones included (is_deleted, enabled) */
export const listServers = () => request('GET', '/api/admin/servers');

/** GET /api/admin/servers/{id} -> ServerListOut */
export const getServer = (id) => request('GET', `/api/admin/servers/${id}`);

/** GET /api/admin/servers/{id}/tools -> ToolOut[] */
export const listServerTools = (id) => request('GET', `/api/admin/servers/${id}/tools`);

/**
 * POST /api/admin/servers with ServerCreate { server_name, server_url, transport, timeout_seconds, enabled, auth? }
 * auth (AuthIn) is optional; leave it out (or send { auth_type: 'none' }) for no upstream auth.
 */
export const registerServer = ({ server_name, server_url, transport, timeout_seconds, enabled, auth }) =>
  request('POST', '/api/admin/servers', {
    body: { server_name, server_url, transport, timeout_seconds, enabled, ...(auth ? { auth } : {}) },
  });

/** PATCH /api/admin/servers/{id} with ServerUpdate: only the fields to change. */
export const updateServer = (id, changes) => request('PATCH', `/api/admin/servers/${id}`, { body: changes });

/** DELETE /api/admin/servers/{id} (soft delete) -> ServerDeletedOut { server, deleted_by, deleted_at } */
export const deleteServer = (id) => request('DELETE', `/api/admin/servers/${id}`);

/** POST /api/admin/servers/{id}/restore -> ServerOut */
export const restoreServer = (id) => request('POST', `/api/admin/servers/${id}/restore`);

/* ---------- Tools (admin) ---------- */

/** GET /api/admin/tools?server_id= -> ToolOut[] (removed tools tagged is_removed, filtered-out ones hidden) */
export const listTools = ({ server_id } = {}) => request('GET', `/api/admin/tools${query({ server_id })}`);

/** GET /api/admin/tools/{id} -> ToolOut */
export const getTool = (id) => request('GET', `/api/admin/tools/${id}`);

/** GET /api/admin/tools/{id}/changes -> ToolChangeOut[], newest first */
export const getToolChanges = (id) => request('GET', `/api/admin/tools/${id}/changes`);

/* ---------- Gateway API keys ---------- */

/** GET /api/admin/keys?user_id= -> KeyListOut[]: your keys and your users' keys, deleted ones included */
export const listKeys = ({ user_id } = {}) => request('GET', `/api/admin/keys${query({ user_id })}`);

/** GET /api/admin/keys/{id} -> KeyListOut */
export const getKey = (id) => request('GET', `/api/admin/keys/${id}`);

/**
 * POST /api/keys with KeyCreate { key_name, server_ids? }.
 * Admins must leave server_ids out (their keys reach every server they added); users must send at least one.
 * @returns KeyCreatedOut, including the plain api_key (returned only this once)
 */
export function createKey({ key_name, server_ids }) {
  const body = server_ids?.length ? { key_name, server_ids } : { key_name };
  return request('POST', '/api/keys', { body });
}

/** DELETE /api/admin/keys/{id} (soft delete) -> KeyDeletedOut */
export const deleteKey = (id) => request('DELETE', `/api/admin/keys/${id}`);

/** POST /api/admin/keys/{id}/restore -> KeyOut */
export const restoreKey = (id) => request('POST', `/api/admin/keys/${id}/restore`);

/** PATCH /api/admin/keys/{id}/servers with KeyServersUpdate { add, remove } -> KeyOut */
export const updateKeyServers = (id, { add = [], remove = [] }) =>
  request('PATCH', `/api/admin/keys/${id}/servers`, { body: { add, remove } });

/** POST /api/admin/keys/{id}/rotate -> KeyCreatedOut with the new plain api_key */
export const rotateKey = (id) => request('POST', `/api/admin/keys/${id}/rotate`);

/* ---------- Users (admin) ---------- */

/** GET /api/admin/users -> UserListOut[]: users you created, deleted ones included */
export const listUsers = () => request('GET', '/api/admin/users');

/** GET /api/admin/users/{id} -> UserDetailOut: the user and all their keys */
export const getUser = (id) => request('GET', `/api/admin/users/${id}`);

/** POST /api/admin/users with RegisterRequest { user_name, password } -> UserOut */
export const createUser = ({ user_name, password }) =>
  request('POST', '/api/admin/users', { body: { user_name, password } });

/** DELETE /api/admin/users/{id} -> UserDeletedOut { user, deleted_by, deleted_at, api_keys_revoked } */
export const deleteUser = (id) => request('DELETE', `/api/admin/users/${id}`);

/** POST /api/admin/users/{id}/restore -> UserOut (their keys stay revoked) */
export const restoreUser = (id) => request('POST', `/api/admin/users/${id}/restore`);

/** PATCH /api/admin/users/{id}/password with PasswordReset { new_password } -> UserOut */
export const resetUserPassword = (id, new_password) =>
  request('PATCH', `/api/admin/users/${id}/password`, { body: { new_password } });

/* ---------- Tool usage ---------- */

/**
 * Usage filters shared by the admin and user routes. Dates are 'YYYY-MM-DD' from <input type="date">, taken as
 * whole UTC days: start at 00:00, end at the end of that day.
 */
function usageParams({ start, end, server_id, tool_id, user_id, key_id, status } = {}) {
  const day = (d, add = 0) => {
    if (!d) return undefined;
    const t = new Date(`${d}T00:00:00Z`);
    t.setUTCDate(t.getUTCDate() + add);
    return t.toISOString();
  };
  return { start: day(start), end: day(end, 1), server_id, tool_id, user_id, key_id, status };
}

/** GET /api/admin/usage -> UsageSummaryOut (totals, by_server, by_tool, by_user) */
export const getUsage = (filters) => request('GET', `/api/admin/usage${query(usageParams(filters))}`);

/** GET /api/admin/usage/calls -> CallPageOut { total, limit, offset, items } */
export const getCalls = (filters, { limit = 50, offset = 0 } = {}) =>
  request('GET', `/api/admin/usage/calls${query({ ...usageParams(filters), limit, offset })}`);

/* ---------- The user's own views (user accounts only) ---------- */

/** GET /api/user/servers -> UserServerOut[]: your admin's enabled, live servers */
export const listMyServers = () => request('GET', '/api/user/servers');

/** GET /api/user/tools?server_id= -> UserToolOut[]: tools you can call */
export const listMyTools = ({ server_id } = {}) => request('GET', `/api/user/tools${query({ server_id })}`);

/** GET /api/user/servers/{id}/tools -> UserToolOut[] */
export const listMyServerTools = (id) => request('GET', `/api/user/servers/${id}/tools`);

/** GET /api/user/keys -> UserKeyOut[]: your live keys */
export const listMyKeys = () => request('GET', '/api/user/keys');

/** GET /api/user/usage -> MyUsageSummaryOut (totals, by_server, by_tool, by_key) */
export const getMyUsage = (filters) => request('GET', `/api/user/usage${query(usageParams(filters))}`);

/** GET /api/user/usage/calls -> CallPageOut */
export const getMyCalls = (filters, { limit = 50, offset = 0 } = {}) =>
  request('GET', `/api/user/usage/calls${query({ ...usageParams(filters), limit, offset })}`);

/* ---------- Helpers ---------- */

/** "add, server_1__sub\nmul" -> ['add', 'server_1__sub', 'mul'] */
export const parseNames = (text) =>
  String(text || '')
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

/** MCP client config (Claude Desktop / Cursor / VS Code style) for a gateway API key. */
export function clientConfig(name, apiKey) {
  const key = String(name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'mcp-gateway';
  return JSON.stringify(
    {
      mcpServers: {
        [key]: {
          type: 'http',
          url: GATEWAY_MCP_URL || '<gateway MCP URL>',
          headers: { Authorization: `Bearer ${apiKey || '<your API key>'}` },
        },
      },
    },
    null,
    2
  );
}

/** The backend sends UTC times without a zone ("2026-11-19T09:20:52"); read them as UTC. */
export function parseTime(iso) {
  if (!iso) return null;
  const s = String(iso);
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}

export const formatDate = (iso) =>
  iso ? parseTime(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '-';

export const formatDateTime = (iso) =>
  iso
    ? parseTime(iso).toLocaleString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : '-';

/** 2608 -> "2.61 s", 921 -> "921 ms" */
export function formatMs(ms) {
  if (ms === null || ms === undefined) return '-';
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

/** "3 minutes ago" style */
export function timeAgo(iso) {
  if (!iso) return 'never';
  const sec = Math.round((Date.now() - parseTime(iso).getTime()) / 1000);
  if (sec < 60) return 'just now';
  const units = [
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ];
  for (const [name, size] of units) {
    const n = Math.floor(sec / size);
    if (n >= 1) return `${n} ${name}${n === 1 ? '' : 's'} ago`;
  }
  return 'just now';
}
