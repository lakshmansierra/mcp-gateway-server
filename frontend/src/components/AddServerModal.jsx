import { useState } from 'react';
import { Server } from 'lucide-react';
import Modal from './Modal.jsx';
import { parseNames, registerServer, SERVER_NAME_PATTERN, TRANSPORTS, updateServer } from '../services/mcpService.js';

const EMPTY = { server_name: '', server_url: '', transport: 'streamable_http', timeout_seconds: '60', enabled: true, include_tools: '', exclude_tools: '' };

const fromServer = (s) => ({
  server_name: s.server_name,
  server_url: s.server_url,
  transport: s.transport,
  timeout_seconds: String(s.timeout_seconds),
  enabled: s.enabled,
  include_tools: (s.include_tools || []).join(', '),
  exclude_tools: (s.exclude_tools || []).join(', '),
});

const sameList = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

/**
 * Add (POST /api/admin/servers) or, with `server`, edit (PATCH /api/admin/servers/{id}) an MCP server.
 * Edits send only the fields that changed.
 */
export default function AddServerModal({ server, onClose, onSaved }) {
  const editing = !!server;
  const [form, setForm] = useState(() => (editing ? fromServer(server) : EMPTY));
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState('');

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  const validate = () => {
    const er = {};
    const name = form.server_name.trim();
    if (!name) er.server_name = 'Server name is required';
    else if (name.length > 100) er.server_name = 'At most 100 characters';
    else if (!SERVER_NAME_PATTERN.test(name)) er.server_name = 'Use only letters, digits, "_" and "-"';
    if (!form.server_url.trim()) er.server_url = 'Endpoint URL is required';
    else if (!/^https?:\/\/\S+$/i.test(form.server_url.trim())) er.server_url = 'Enter a valid http(s) URL';
    const t = Number(form.timeout_seconds);
    if (!Number.isInteger(t) || t <= 0 || t > 3600) er.timeout_seconds = 'A whole number from 1 to 3600';
    if (editing && parseNames(form.include_tools).length === 0) er.include_tools = 'Give at least one tool name, or * for every tool';
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const payload = () => ({
    server_name: form.server_name.trim(),
    server_url: form.server_url.trim(),
    transport: form.transport,
    timeout_seconds: Number(form.timeout_seconds),
    enabled: form.enabled,
  });

  /** ServerUpdate: only what differs from the current server. */
  const changes = () => {
    const next = payload();
    const out = {};
    for (const [k, v] of Object.entries(next)) if (v !== server[k]) out[k] = v;
    const include = parseNames(form.include_tools);
    const exclude = parseNames(form.exclude_tools);
    if (!sameList(include, server.include_tools || [])) out.include_tools = include;
    if (!sameList(exclude, server.exclude_tools || [])) out.exclude_tools = exclude;
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
