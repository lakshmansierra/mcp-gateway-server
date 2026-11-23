import { User } from 'lucide-react';
import Modal from './Modal.jsx';
import { LoadError, TableState } from './Common.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { formatDate, formatDateTime, getUser } from '../services/mcpService.js';

/** Tags for the servers a key reaches; deleted or disabled servers are marked. */
export function KeyServerTags({ apiKey }) {
  if (apiKey.all_servers) return <span className="tag">All your servers</span>;
  if (!apiKey.servers.length) return <span className="muted">none</span>;
  return (
    <div className="tag-list">
      {apiKey.servers.map((s) => {
        const state = s.is_deleted ? 'deleted' : s.enabled ? null : 'disabled';
        return (
          <span key={s.id} className={`tag ${state ? 'tag-warn' : ''}`} title={state ? `This server is ${state}` : `Server #${s.id}`}>
            {s.server_name}
            {state ? ` (${state})` : ''}
          </span>
        );
      })}
    </div>
  );
}

/** GET /api/admin/users/{id}: the account and every key it owns (revoked ones too). */
export default function UserDetailModal({ userId, onClose }) {
  const { data, error, loading, reload } = useLoader(() => getUser(userId), [userId]);
  const u = data;

  return (
    <Modal title={u ? u.user_name : 'User'} subtitle={u ? `User #${u.id}` : ''} icon={<User size={20} />} onClose={onClose} width={760}>
      <LoadError error={error} onRetry={reload} />
      {u && (
        <div className="detail-grid" style={{ padding: '0 0 16px' }}>
          <div>
            <span>Status</span>
            <strong>
              <span className={`status-pill ${u.is_deleted ? 'deleted' : 'active'}`}>{u.is_deleted ? 'Deleted' : 'Active'}</span>
            </strong>
          </div>
          <div><span>Type</span><strong>{u.type}</strong></div>
          <div><span>Created</span><strong>{formatDate(u.created_at)}</strong></div>
          <div><span>Live keys</span><strong>{u.key_count}</strong></div>
          {u.is_deleted && <div><span>Deleted</span><strong>{formatDateTime(u.deleted_at)}</strong></div>}
        </div>
      )}
      <div className="table-scroll" style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Key</th>
              <th>Servers</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            <TableState loading={loading} empty={!u || u.keys.length === 0} cols={5} emptyText="No API keys" />
            {(u?.keys || []).map((k) => (
              <tr key={k.id}>
                <td className="id-cell">{k.id}</td>
                <td><strong>{k.key_name}</strong></td>
                <td><KeyServerTags apiKey={k} /></td>
                <td><span className={`status-pill ${k.is_deleted ? 'deleted' : 'active'}`}>{k.is_deleted ? 'Revoked' : 'Active'}</span></td>
                <td className="nowrap">{formatDate(k.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="modal-actions">
        <button className="btn btn-primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
