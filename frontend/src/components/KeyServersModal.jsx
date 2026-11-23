import { useMemo, useState } from 'react';
import { Server } from 'lucide-react';
import Modal from './Modal.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { listServers, updateKeyServers } from '../services/mcpService.js';

/**
 * PATCH /api/admin/keys/{id}/servers with KeyServersUpdate { add, remove }.
 * Choices: your enabled, live servers (GET /api/admin/servers), plus whatever the key has now, so a deleted or
 * disabled server can still be taken off it. Tick what the key should reach; only the difference is sent.
 */
export default function KeyServersModal({ apiKey, onClose, onSaved }) {
  const current = useMemo(() => apiKey.servers.map((s) => s.id), [apiKey]);
  const servers = useLoader(listServers, [], []);
  const [checked, setChecked] = useState(() => new Set(current));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const options = useMemo(() => {
    const byId = new Map(apiKey.servers.map((s) => [s.id, s]));
    for (const s of servers.data) if ((s.enabled && !s.is_deleted) || byId.has(s.id)) byId.set(s.id, s);
    return [...byId.values()].sort((a, b) => a.server_name.localeCompare(b.server_name));
  }, [apiKey, servers.data]);

  const flip = (id) =>
    setChecked((sel) => {
      const next = new Set(sel);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const submit = async (e) => {
    e.preventDefault();
    const add = [...checked].filter((id) => !current.includes(id));
    const remove = current.filter((id) => !checked.has(id));
    if (checked.size === 0) {
      setError('A key must keep at least one server. Revoke the key instead.');
      return;
    }
    if (!add.length && !remove.length) {
      onClose();
      return;
    }
    setBusy(true);
    setError('');
    try {
      onSaved(await updateKeyServers(apiKey.id, { add, remove }));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const note = (s) => (s.is_deleted ? ' · deleted' : !s.enabled ? ' · disabled' : '');

  return (
    <Modal title="Edit Key Servers" subtitle={`${apiKey.key_name} (#${apiKey.id}) · ${apiKey.user_name}`} icon={<Server size={20} />} onClose={onClose} width={560}>
      <form onSubmit={submit} className="form" noValidate>
        <div className="field">
          <span>Servers this key reaches</span>
          {servers.error && <div className="alert-error">{servers.error}</div>}
          {servers.loading && options.length === 0 ? (
            <p className="field-hint">Loading servers...</p>
          ) : (
            <ul className="selected-list server-pick">
              {options.map((s) => (
                <li key={s.id}>
                  <label className="checkbox">
                    <input type="checkbox" checked={checked.has(s.id)} onChange={() => flip(s.id)} />
                    <span>
                      <strong>{s.server_name}</strong> <small className="muted">#{s.id}{note(s)}</small>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <small className="field-hint">Only enabled servers can be added. Deleted or disabled ones can only be removed.</small>
        </div>

        {error && <div className="alert-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Saving...' : 'Save Servers'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
