import { useState } from 'react';
import { Server } from 'lucide-react';
import Modal from './Modal.jsx';
import { addServer, AUTH_TYPES, TRANSPORTS } from '../services/mcpService.js';

const EMPTY = { name: '', url: '', transport: 'streamable-http', authType: 'none', description: '', status: 'active' };

export default function AddServerModal({ onClose, onAdded }) {
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState('');

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  const validate = () => {
    const er = {};
    if (!form.name.trim()) er.name = 'Server name is required';
    if (!form.url.trim()) er.url = 'Endpoint URL is required';
    else if (!/^https?:\/\/\S+$/i.test(form.url.trim())) er.url = 'Enter a valid http(s) URL';
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    setApiError('');
    try {
      const server = await addServer(form);
      onAdded(server);
    } catch (err) {
      setApiError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="Add MCP Server"
      subtitle="Register a new MCP server with the gateway"
      icon={<Server size={20} />}
      onClose={onClose}
    >
      <form onSubmit={submit} className="form" noValidate>
        <label className="field">
          <span>Server name</span>
          <input value={form.name} onChange={set('name')} placeholder="e.g. GitHub MCP" autoFocus />
          {errors.name && <em className="field-error">{errors.name}</em>}
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
            <span>Authentication</span>
            <select value={form.authType} onChange={set('authType')}>
              {Object.entries(AUTH_TYPES).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </label>
        </div>

        <label className="field">
          <span>Endpoint URL</span>
          <input
            value={form.url}
            onChange={set('url')}
            placeholder={form.transport === 'sse' ? 'https://my-server.example.com/sse' : 'https://my-server.example.com/mcp'}
          />
          {errors.url && <em className="field-error">{errors.url}</em>}
        </label>

        <label className="field">
          <span>
            Description <small className="muted">(optional)</small>
          </span>
          <textarea rows={2} value={form.description} onChange={set('description')} placeholder="What tools does this server expose?" />
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.status === 'active'}
            onChange={(e) => setForm((f) => ({ ...f, status: e.target.checked ? 'active' : 'inactive' }))}
          />
          <span>Enable immediately</span>
        </label>

        {apiError && <div className="alert-error">{apiError}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? 'Adding...' : 'Add Server'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
