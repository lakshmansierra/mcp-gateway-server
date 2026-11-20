import { useState } from 'react';
import { Check, Copy, KeyRound } from 'lucide-react';
import Modal from './Modal.jsx';
import KeyCell from './KeyCell.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { clientConfig, createKey, GATEWAY_MCP_URL, NAME_PATTERN, parseIds } from '../services/mcpService.js';

export function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard blocked */
    }
  };
  return (
    <button type="button" className="icon-btn subtle" onClick={copy} title={label} aria-label={label}>
      {copied ? <Check size={16} /> : <Copy size={16} />}
    </button>
  );
}

/**
 * Endpoint, key and client config for a gateway API key.
 * `apiKey` is only known right after create / rotate; the backend never returns it again.
 * `servers` is a list of labels, or null for an admin key (every server its admin registered).
 */
export function ApiDetails({ name, apiKey, servers }) {
  const config = clientConfig(name, apiKey);
  return (
    <div className="form">
      {apiKey && <div className="alert-warn">Copy the API key now. It is shown only once and can't be retrieved later.</div>}
      <div className="field">
        <span>Gateway endpoint</span>
        <div className="key-cell">
          <code className="key-value">{GATEWAY_MCP_URL || 'VITE_GATEWAY_MCP_URL is not set'}</code>
          {GATEWAY_MCP_URL && <CopyButton text={GATEWAY_MCP_URL} label="Copy endpoint" />}
        </div>
      </div>
      <div className="field">
        <span>API key</span>
        {apiKey ? (
          <KeyCell value={apiKey} />
        ) : (
          <p className="field-hint">Shown only when the key is created or rotated. Use the key you saved then.</p>
        )}
      </div>
      <div className="field">
        <span>Servers included</span>
        <div className="tag-list">
          {servers ? servers.map((n) => <span key={n} className="tag">{n}</span>) : <span className="tag">All servers registered by the admin</span>}
        </div>
      </div>
      <div className="field">
        <div className="field-label-row">
          <span>MCP client config</span>
          <CopyButton text={config} label="Copy config" />
        </div>
        <pre className="code-block">{config}</pre>
      </div>
    </div>
  );
}

/** POST /api/keys. Users pick server IDs; admin keys reach every server the admin registered. */
export default function GenerateApiModal({ onClose, onGenerated, serverLabel = (id) => `#${id}` }) {
  const { isAdmin } = useAuth();
  const [name, setName] = useState('');
  const [ids, setIds] = useState('');
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    const er = {};
    const key_name = name.trim();
    if (!key_name) er.name = 'Key name is required';
    else if (key_name.length > 100) er.name = 'At most 100 characters';
    else if (!NAME_PATTERN.test(key_name)) er.name = 'Use only letters, digits, ".", "_" and "-"';
    let server_ids;
    if (!isAdmin) {
      try {
        server_ids = parseIds(ids);
        if (server_ids.length === 0) er.ids = 'Enter at least one server ID';
      } catch (err) {
        er.ids = err.message;
      }
    }
    setErrors(er);
    if (Object.keys(er).length) return;

    setBusy(true);
    setError('');
    try {
      const out = await createKey({ key_name, server_ids });
      setResult(out);
      onGenerated?.(out);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <Modal title="Gateway API generated" subtitle={result.key_name} icon={<KeyRound size={20} />} onClose={onClose} width={600}>
        <ApiDetails name={result.key_name} apiKey={result.api_key} servers={result.all_servers ? null : result.server_ids.map(serverLabel)} />
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={onClose}>Done</button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Generate Gateway API"
      subtitle={isAdmin ? 'A key for every server you registered' : 'One key for the servers you choose'}
      icon={<KeyRound size={20} />}
      onClose={onClose}
      width={560}
    >
      <form onSubmit={submit} className="form" noValidate>
        <label className="field">
          <span>Key name</span>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setErrors((er) => ({ ...er, name: undefined }));
            }}
            placeholder="e.g. claude-desktop"
            maxLength={100}
            autoFocus
          />
          {errors.name ? <em className="field-error">{errors.name}</em> : <small className="field-hint">Unique among your keys, e.g. dev or claude-desktop</small>}
        </label>

        {isAdmin ? (
          <div className="alert-info">Admin keys reach every MCP server you registered, enabled or disabled.</div>
        ) : (
          <label className="field">
            <span>Server IDs</span>
            <input
              value={ids}
              onChange={(e) => {
                setIds(e.target.value);
                setErrors((er) => ({ ...er, ids: undefined }));
              }}
              placeholder="e.g. 3, 7"
            />
            {errors.ids ? (
              <em className="field-error">{errors.ids}</em>
            ) : (
              <small className="field-hint">IDs of enabled servers your admin registered, separated by commas. Ask your admin for them.</small>
            )}
          </label>
        )}

        {error && <div className="alert-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Generating...' : 'Generate API'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
