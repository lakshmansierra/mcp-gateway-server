import { useState } from 'react';
import { Server, ShieldCheck } from 'lucide-react';
import Modal from './Modal.jsx';
import {
  ADD_AUTH_TO,
  AUTH_TYPES,
  CLIENT_AUTH,
  OAUTH_GRANTS,
  parseNames,
  registerServer,
  SERVER_NAME_PATTERN,
  TRANSPORTS,
  updateServer,
} from '../services/mcpService.js';

// Auth fields default to empty; secrets (token/password/client_secret) are never pre-filled on edit.
const AUTH_EMPTY = {
  auth_type: 'none',
  token: '',
  header_prefix: 'Bearer',
  username: '',
  password: '',
  oauth_grant_type: 'client_credentials',
  add_auth_data_to: 'header',
  token_url: '',
  client_id: '',
  client_secret: '',
  scope: '',
  client_authentication: 'basic_header',
};

const EMPTY = {
  server_name: '',
  server_url: '',
  transport: 'streamable_http',
  timeout_seconds: '60',
  enabled: true,
  include_tools: '',
  exclude_tools: '',
  ...AUTH_EMPTY,
};

const fromServer = (s) => {
  const a = s.auth || {};
  return {
    server_name: s.server_name,
    server_url: s.server_url,
    transport: s.transport,
    timeout_seconds: String(s.timeout_seconds),
    enabled: s.enabled,
    include_tools: (s.include_tools || []).join(', '),
    exclude_tools: (s.exclude_tools || []).join(', '),
    // auth: non-secret values prefill; secrets stay blank (placeholder shows "configured")
    ...AUTH_EMPTY,
    auth_type: a.auth_type || 'none',
    header_prefix: a.header_prefix || 'Bearer',
    username: a.username || '',
    oauth_grant_type: a.oauth_grant_type || 'client_credentials',
    add_auth_data_to: a.add_auth_data_to || 'header',
    token_url: a.token_url || '',
    client_id: a.client_id || '',
    scope: a.scope || '',
    client_authentication: a.client_authentication || 'basic_header',
  };
};

const sameList = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
const isUrl = (v) => /^https?:\/\/\S+$/i.test(v.trim());

/**
 * Add (POST /api/admin/servers) or, with `server`, edit (PATCH /api/admin/servers/{id}) an MCP server.
 * Edits send only the fields that changed. Upstream auth (no auth / basic / bearer / oauth2) is set here too.
 */
export default function AddServerModal({ server, onClose, onSaved }) {
  const editing = !!server;
  const [form, setForm] = useState(() => (editing ? fromServer(server) : EMPTY));
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState('');
  // On edit we only send `auth` when the admin actually touches it (otherwise the stored config, incl. secrets,
  // is left exactly as it was). Any change to an auth field, including the type dropdown, flips this.
  const [authDirty, setAuthDirty] = useState(false);

  const has = server?.auth || {}; // which secrets are already configured (has_token, etc.)

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  // Like set(), but also marks the auth block dirty so an edit includes it.
  const setAuth = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
    setAuthDirty(true);
  };

  // Whether the auth block will be sent: always on create (unless 'none'), only when touched on edit.
  const sendAuth = editing ? authDirty : form.auth_type !== 'none';

  const validate = () => {
    const er = {};
    const name = form.server_name.trim();
    if (!name) er.server_name = 'Server name is required';
    else if (name.length > 100) er.server_name = 'At most 100 characters';
    else if (!SERVER_NAME_PATTERN.test(name)) er.server_name = 'Use only letters, digits, "_" and "-"';
    if (!form.server_url.trim()) er.server_url = 'Endpoint URL is required';
    else if (!isUrl(form.server_url)) er.server_url = 'Enter a valid http(s) URL';
    const t = Number(form.timeout_seconds);
    if (!Number.isInteger(t) || t <= 0 || t > 3600) er.timeout_seconds = 'A whole number from 1 to 3600';
    if (editing && parseNames(form.include_tools).length === 0) er.include_tools = 'Give at least one tool name, or * for every tool';

    if (sendAuth && form.auth_type !== 'none') {
      if (form.auth_type === 'bearer' && !form.token.trim()) er.token = 'Token is required';
      if (form.auth_type === 'basic' && !form.username.trim()) er.username = 'Username is required';
      if (form.auth_type === 'oauth2') {
        if (!form.token_url.trim()) er.token_url = 'Token URL is required';
        else if (!isUrl(form.token_url)) er.token_url = 'Enter a valid http(s) URL';
        if (!form.client_id.trim()) er.client_id = 'Client ID is required';
        if (!form.client_secret.trim()) er.client_secret = 'Client secret is required';
        if (form.oauth_grant_type === 'password') {
          if (!form.username.trim()) er.username = 'Username is required';
          if (!form.password.trim()) er.password = 'Password is required';
        }
      }
    }
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  /** The AuthIn object for the chosen type (only the fields that type needs). */
  const authPayload = () => {
    const a = form.auth_type;
    if (a === 'none') return { auth_type: 'none' };
    if (a === 'bearer') return { auth_type: 'bearer', token: form.token, header_prefix: form.header_prefix || 'Bearer' };
    if (a === 'basic') return { auth_type: 'basic', username: form.username, password: form.password };
    const base = {
      auth_type: 'oauth2',
      oauth_grant_type: form.oauth_grant_type,
      add_auth_data_to: form.add_auth_data_to,
      header_prefix: form.header_prefix || 'Bearer',
      token_url: form.token_url,
      client_id: form.client_id,
      client_secret: form.client_secret,
      scope: form.scope,
      client_authentication: form.client_authentication,
    };
    if (form.oauth_grant_type === 'password') {
      base.username = form.username;
      base.password = form.password;
    }
    return base;
  };

  const payload = () => ({
    server_name: form.server_name.trim(),
    server_url: form.server_url.trim(),
    transport: form.transport,
    timeout_seconds: Number(form.timeout_seconds),
    enabled: form.enabled,
    ...(sendAuth ? { auth: authPayload() } : {}),
  });

  /** ServerUpdate: only what differs from the current server (auth only when touched). */
  const changes = () => {
    const base = {
      server_name: form.server_name.trim(),
      server_url: form.server_url.trim(),
      transport: form.transport,
      timeout_seconds: Number(form.timeout_seconds),
      enabled: form.enabled,
    };
    const out = {};
    for (const [k, v] of Object.entries(base)) if (v !== server[k]) out[k] = v;
    const include = parseNames(form.include_tools);
    const exclude = parseNames(form.exclude_tools);
    if (!sameList(include, server.include_tools || [])) out.include_tools = include;
    if (!sameList(exclude, server.exclude_tools || [])) out.exclude_tools = exclude;
    if (authDirty) out.auth = authPayload();
    return out;
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    let body;
    if (editing) {
      body = changes();
      if (Object.keys(body).length === 0) {
        onClose();
        return;
      }
    }
    setSubmitting(true);
    setApiError('');
    try {
      const saved = editing ? await updateServer(server.id, body) : await registerServer(payload());
      onSaved(saved);
    } catch (err) {
      setApiError(err.message);
      setSubmitting(false);
    }
  };

  const secretPlaceholder = (configured) => (editing && configured ? '•••••••••• (leave blank to keep)' : '');

  return (
    <Modal
      title={editing ? 'Edit MCP Server' : 'Add MCP Server'}
      subtitle={editing ? `Server #${server.id}` : 'Register a new MCP server with the gateway'}
      icon={<Server size={20} />}
      onClose={onClose}
    >
      <form onSubmit={submit} className="form" noValidate>
        <label className="field">
          <span>Server name</span>
          <input value={form.server_name} onChange={set('server_name')} placeholder="e.g. github_mcp" maxLength={100} autoFocus />
          {errors.server_name ? (
            <em className="field-error">{errors.server_name}</em>
          ) : (
            <small className="field-hint">
              Becomes the tool prefix: <code>{form.server_name.trim() || 'name'}__tool</code>
            </small>
          )}
        </label>

        <div className="field-row">
          <label className="field">
            <span>Transport</span>
            <select value={form.transport} onChange={set('transport')}>
              {Object.entries(TRANSPORTS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Timeout (seconds)</span>
            <input type="number" min={1} max={3600} step={1} value={form.timeout_seconds} onChange={set('timeout_seconds')} />
            {errors.timeout_seconds && <em className="field-error">{errors.timeout_seconds}</em>}
          </label>
        </div>

        <label className="field">
          <span>Endpoint URL</span>
          <input
            value={form.server_url}
            onChange={set('server_url')}
            placeholder={form.transport === 'sse' ? 'https://my-server.example.com/sse' : 'https://my-server.example.com/mcp'}
          />
          {errors.server_url && <em className="field-error">{errors.server_url}</em>}
        </label>

        {editing && (
          <div className="field-row">
            <label className="field">
              <span>Include tools</span>
              <textarea rows={2} value={form.include_tools} onChange={set('include_tools')} placeholder="* for every tool" />
              {errors.include_tools ? (
                <em className="field-error">{errors.include_tools}</em>
              ) : (
                <small className="field-hint">Full tool names, comma separated, or *</small>
              )}
            </label>
            <label className="field">
              <span>Exclude tools</span>
              <textarea rows={2} value={form.exclude_tools} onChange={set('exclude_tools')} placeholder="None" />
              <small className="field-hint">Full tool names to hide</small>
            </label>
          </div>
        )}

        {/* ---- Upstream authentication ---- */}
        <fieldset className="auth-section">
          <legend><ShieldCheck size={15} /> Authentication</legend>
          <small className="field-hint">How the gateway authenticates to this server. Sent with every request it makes to it.</small>

          <label className="field">
            <span>Auth type</span>
            <select
              value={form.auth_type}
              onChange={(e) => {
                setForm((f) => ({ ...f, auth_type: e.target.value }));
                setErrors({});
                setAuthDirty(true);
              }}
            >
              {Object.entries(AUTH_TYPES).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>

          {form.auth_type === 'bearer' && (
            <>
              <label className="field">
                <span>Token</span>
                <input type="password" value={form.token} onChange={setAuth('token')} placeholder={secretPlaceholder(has.has_token)} autoComplete="off" />
                {errors.token && <em className="field-error">{errors.token}</em>}
              </label>
              <label className="field">
                <span>Header prefix</span>
                <input value={form.header_prefix} onChange={setAuth('header_prefix')} placeholder="Bearer" />
                <small className="field-hint">Sent as <code>Authorization: {form.header_prefix || 'Bearer'} &lt;token&gt;</code></small>
              </label>
            </>
          )}

          {form.auth_type === 'basic' && (
            <div className="field-row">
              <label className="field">
                <span>Username</span>
                <input value={form.username} onChange={setAuth('username')} autoComplete="off" />
                {errors.username && <em className="field-error">{errors.username}</em>}
              </label>
              <label className="field">
                <span>Password</span>
                <input type="password" value={form.password} onChange={setAuth('password')} placeholder={secretPlaceholder(has.has_password)} autoComplete="off" />
                {errors.password && <em className="field-error">{errors.password}</em>}
              </label>
            </div>
          )}

          {form.auth_type === 'oauth2' && (
            <>
              <div className="field-row">
                <label className="field">
                  <span>Grant type</span>
                  <select value={form.oauth_grant_type} onChange={setAuth('oauth_grant_type')}>
                    {Object.entries(OAUTH_GRANTS).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Add auth data to</span>
                  <select value={form.add_auth_data_to} onChange={setAuth('add_auth_data_to')}>
                    {Object.entries(ADD_AUTH_TO).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="field">
                <span>Access token URL</span>
                <input value={form.token_url} onChange={setAuth('token_url')} placeholder="https://auth.example.com/oauth/token" />
                {errors.token_url && <em className="field-error">{errors.token_url}</em>}
              </label>
              <div className="field-row">
                <label className="field">
                  <span>Client ID</span>
                  <input value={form.client_id} onChange={setAuth('client_id')} autoComplete="off" />
                  {errors.client_id && <em className="field-error">{errors.client_id}</em>}
                </label>
                <label className="field">
                  <span>Client secret</span>
                  <input type="password" value={form.client_secret} onChange={setAuth('client_secret')} placeholder={secretPlaceholder(has.has_client_secret)} autoComplete="off" />
                  {errors.client_secret && <em className="field-error">{errors.client_secret}</em>}
                </label>
              </div>
              {form.oauth_grant_type === 'password' && (
                <div className="field-row">
                  <label className="field">
                    <span>Username</span>
                    <input value={form.username} onChange={setAuth('username')} autoComplete="off" />
                    {errors.username && <em className="field-error">{errors.username}</em>}
                  </label>
                  <label className="field">
                    <span>Password</span>
                    <input type="password" value={form.password} onChange={setAuth('password')} placeholder={secretPlaceholder(has.has_password)} autoComplete="off" />
                    {errors.password && <em className="field-error">{errors.password}</em>}
                  </label>
                </div>
              )}
              <div className="field-row">
                <label className="field">
                  <span>Scope</span>
                  <input value={form.scope} onChange={setAuth('scope')} placeholder="optional, space separated" />
                </label>
                <label className="field">
                  <span>Client authentication</span>
                  <select value={form.client_authentication} onChange={setAuth('client_authentication')}>
                    {Object.entries(CLIENT_AUTH).map(([v, l]) => (
                      <option key={v} value={v}>{l}</option>
                    ))}
                  </select>
                </label>
              </div>
            </>
          )}

          {editing && form.auth_type !== 'none' && (
            <small className="field-hint">Leave secret fields blank to keep the stored value; fill them to replace it.</small>
          )}
        </fieldset>

        <label className="checkbox">
          <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))} />
          <span>{editing ? 'Enabled' : 'Enable immediately'}</span>
        </label>

        {apiError && <div className="alert-error">{apiError}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? (editing ? 'Saving...' : 'Adding...') : editing ? 'Save Changes' : 'Add Server'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
