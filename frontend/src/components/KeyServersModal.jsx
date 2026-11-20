import { useMemo, useState } from 'react';
import { Server } from 'lucide-react';
import Modal from './Modal.jsx';
import { parseIds, updateKeyServers } from '../services/mcpService.js';

/**
 * PATCH /api/admin/keys/{id}/servers with KeyServersUpdate { add, remove }.
 * Tick the servers the key should reach; the modal sends the difference from what it has now.
 */
export default function KeyServersModal({ apiKey, servers, onClose, onSaved }) {
  const current = apiKey.server_ids;
  const [checked, setChecked] = useState(() => new Set(current));
  const [extra, setExtra] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Servers the key has now, plus enabled live servers this browser knows about.
  const options = useMemo(() => {
    const byId = new Map(servers.map((s) => [s.id, s]));
    const ids = new Set([...current, ...servers.filter((s) => s.enabled && !s.deleted_at).map((s) => s.id)]);
    return [...ids].sort((a, b) => a - b).map((id) => ({ id, server: byId.get(id) }));
  }, [current, servers]);

  const flip = (id) =>
    setChecked((sel) => {
      const next = new Set(sel);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const submit = async (e) => {
    e.preventDefault();
    let extraIds;
    try {
      extraIds = parseIds(extra);
    } catch (err) {
      setError(err.message);
      return;
    }
    const wanted = new Set([...checked, ...extraIds]);
    const add = [...wanted].filter((id) => !current.includes(id));
    const remove = current.filter((id) => !wanted.has(id));
    if (wanted.size === 0) {
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

  return (
    <Modal title="Edit Key Servers" subtitle={`${apiKey.key_name} (#${apiKey.id})`} icon={<Server size={20} />} onClose={onClose} width={560}>
      <form onSubmit={submit} className="form" noValidate>
        <div className="field">
          <span>Servers this key reaches</span>
          {options.length === 0 ? (
            <p className="field-hint">No servers known in this browser. Add server IDs below.</p>
          ) : (
            <ul className="selected-list">
              {options.map(({ id, server }) => (
                <li key={id}>
                  <label className="checkbox">
                    <input type="checkbox" checked={checked.has(id)} onChange={() => flip(id)} />
                    <span>
                      <strong>{server ? server.server_name : `Server #${id}`}</strong>{' '}
                      <small className="muted">#{id}{server && !server.enabled ? ' · disabled' : ''}</small>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <label className="field">
          <span>
            Other server IDs to add <small className="muted">(optional)</small>
          </span>
          <input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="e.g. 12, 15" />
          <small className="field-hint">Servers must be enabled and registered by the admin who created the key's user.</small>
        </label>

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
