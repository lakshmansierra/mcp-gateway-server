/**
 * HTTP client for the MCP Gateway backend (FastAPI).
 *
 * - Base URL comes from VITE_API_BASE_URL (baked in at build time).
 * - Sends the login token as `Authorization: Bearer <token>` on authenticated calls.
 * - Turns FastAPI errors ({ detail: string } or 422 { detail: [{ loc, msg }] }) into readable messages.
 * - On a 401 from an authenticated call (token expired, revoked, logged out elsewhere) it tells the
 *   AuthContext, which clears the session.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

let getSession = () => null;
let onUnauthorized = () => {};

/** Called by AuthContext so this module can read the current session and report expired tokens. */
export function configureApi({ session, unauthorized }) {
  getSession = session;
  onUnauthorized = unauthorized;
}

export const currentSession = () => getSession();

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function messageFrom(status, data) {
  const detail = data && typeof data === 'object' ? data.detail : null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((e) => {
        const field = (e.loc || []).filter((p) => p !== 'body').join('.');
        const msg = String(e.msg || 'Invalid value').replace(/^Value error, /, '');
        return field ? `${field}: ${msg}` : msg;
      })
      .join('; ');
  }
  if (typeof data === 'string' && data.trim() && data.length < 300) return data;
  return `Request failed (HTTP ${status})`;
}

/**
 * @param {'GET'|'POST'|'PATCH'|'DELETE'} method
 * @param {string} path  e.g. '/api/admin/servers'
 * @param {{ body?: unknown, auth?: boolean }} [options]  auth=false for the login and health routes
 */
export async function request(method, path, { body, auth = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = auth ? getSession()?.token : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      `Cannot reach the backend${API_BASE_URL ? ` at ${API_BASE_URL}` : ''}. Check your connection and try again.`,
      0
    );
  }

  const text = res.status === 204 ? '' : await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const err = new ApiError(messageFrom(res.status, data), res.status, data?.detail);
    if (res.status === 401 && auth) onUnauthorized('Your session has ended. Please sign in again.');
    throw err;
  }
  return data;
}
