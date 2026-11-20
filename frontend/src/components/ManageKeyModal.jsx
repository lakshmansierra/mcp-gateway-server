import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import Modal from './Modal.jsx';
import { ApiDetails } from './GenerateApiModal.jsx';
import { deleteKey, parseIds, restoreKey, rotateKey, updateKeyServers } from '../services/mcpService.js';

const ACTIONS = {
  revoke: { label: 'Revoke', busy: 'Revoking...', danger: true, hint: 'The key stops working at once. It can be restored later.' },
  restore: { label: 'Restore', busy: 'Restoring...', hint: 'The same key value works again with its old servers.' },
  rotate: { label: 'Rotate', busy: 'Rotating...', hint: 'The key gets a new value; the old value stops working at once.' },
  servers: { label: 'Change Servers', busy: 'Saving...', hint: "Add or remove servers on a user's key." },
};

/**
 * Admin actions on a key by its ID, for keys this browser has not seen (e.g. keys your users created):
 * DELETE /api/admin/keys/{id}, POST .../restore, POST .../rotate, PATCH .../servers.
 */
export default function ManageKeyModal({ onClose, onDone, serverLabel }) {
  const [keyId, setKeyId] = useState('');
  const [action, setAction] = useState('revoke');
  const [add, setAdd] = useState('');
  const [remove, setRemove] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [rotated, setRotated] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    const id = Number(keyId);
    if (!Number.isInteger(id) || id <= 0) {
      setError('Enter a valid key ID.');
      return;
    }
    let body;
    if (action === 'servers') {
      try {
        body = { add: parseIds(add), remove: parseIds(remove) };
      } catch (err) {
        setError(err.message);
        return;
      }
      if (!body.add.length && !body.remove.length) {
        setError('Enter server IDs to add or remove.');
        return;
      }
    }
    setBusy(true);
    setError('');
    try {
      if (action === 'revoke') {
        const out = await deleteKey(id);
        onDone(`Key "${out.key_name}" revoked.`);
      } else if (action === 'restore') {
        const out = await restoreKey(id);
        onDone(`Key "${out.key_name}" restored.`);
      } else if (action === 'servers') {
        const out = await updateKeyServers(id, body);
        onDone(`Servers of key "${out.key_name}" updated.`);
      } else {
        const out = await rotateKey(id);
        setRotated(out);
        setBusy(false);
      }
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  if (rotated) {
    return (
      <Modal title="Key rotated" subtitle={rotated.key_name} icon={<KeyRound size={20} />} onClose={() => onDone(`Key "${rotated.key_name}" rotated.`)} width={600}>
        <ApiDetails name={rotated.key_name} apiKey={rotated.api_key} servers={rotated.all_servers ? null : rotated.server_ids.map(serverLabel)} />
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={() => onDone(`Key "${rotated.key_name}" rotated.`)}>Done</button>
        </div>
      </Modal>
    );
  }

  const a = ACTIONS[action];

  return (
    <Modal title="Manage Key by ID" subtitle="Keys you or your users created" icon={<KeyRound size={20} />} onClose={onClose} width={520}>
      <form onSubmit={submit} className="form" noValidate>
        <div className="field-row">
          <label className="field">
            <span>Key ID</span>
            <input type="number" min={1} step={1} value={keyId} onChange={(e) => setKeyId(e.target.value)} placeholder="e.g. 42" autoFocus />
          </label>
          <label className="field">
            <span>Action</span>
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              {Object.entries(ACTIONS).map(([v, x]) => (
                <option key={v} value={v}>{x.label}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="field-hint">{a.hint}</p>

        {action === 'servers' && (
          <div className="field-row">
            <label className="field">
              <span>Add server IDs</span>
              <input value={add} onChange={(e) => setAdd(e.target.value)} placeholder="e.g. 3, 7" />
            </label>
            <label className="field">
              <span>Remove server IDs</span>
              <input value={remove} onChange={(e) => setRemove(e.target.value)} placeholder="e.g. 5" />
            </label>
          </div>
        )}

        {error && <div className="alert-error">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className={`btn ${a.danger ? 'btn-danger' : 'btn-primary'}`} disabled={busy}>
            {busy ? a.busy : a.label}
          </button>
        </div>
      </form>
    </Modal>
  );
}
