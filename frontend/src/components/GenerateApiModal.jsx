import { useState } from 'react';
import { Check, Copy, KeyRound } from 'lucide-react';
import Modal from './Modal.jsx';
import KeyCell from './KeyCell.jsx';
import { clientConfig, generateGatewayApi } from '../services/mcpService.js';

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

export function ApiDetails({ api }) {
  const config = clientConfig(api);
  return (
    <div className="form">
      <div className="field">
        <span>Gateway endpoint</span>
        <div className="key-cell">
          <code className="key-value">{api.endpoint}</code>
          <CopyButton text={api.endpoint} label="Copy endpoint" />
        </div>
      </div>
      <div className="field">
        <span>API key</span>
        <KeyCell value={api.apiKey} />
      </div>
      <div className="field">
        <span>Servers included</span>
        <div className="tag-list">
          {api.serverNames.map((n) => (
            <span key={n} className="tag">{n}</span>
          ))}
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

export default function GenerateApiModal({ servers, onClose, onGenerated }) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const api = await generateGatewayApi({ name, serverIds: servers.map((s) => s.id) });
      setResult(api);
      onGenerated?.(api);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <Modal title="Gateway API generated" subtitle={result.name} icon={<KeyRound size={20} />} onClose={onClose} width={600}>
        <ApiDetails api={result} />
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={onClose}>Done</button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Generate Gateway API"
      subtitle={`One endpoint for ${servers.length} selected server${servers.length === 1 ? '' : 's'}`}
      icon={<KeyRound size={20} />}
      onClose={onClose}
      width={560}
    >
      <form onSubmit={submit} className="form">
        <label className="field">
          <span>
            Name <small className="muted">(optional)</small>
          </span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. My dev workspace" autoFocus />
        </label>

        <div className="field">
          <span>Selected servers</span>
          <ul className="selected-list">
            {servers.map((s) => (
              <li key={s.id}>
                <strong>{s.name}</strong>
                <code className="url">{s.url}</code>
              </li>
            ))}
          </ul>
        </div>

        {error && <div className="alert-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || servers.length === 0}>
            {busy ? 'Generating...' : 'Generate API'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
