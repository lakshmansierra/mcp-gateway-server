import { useMemo, useState } from 'react';
import { FileCode, KeyRound, Plus, RotateCcw, RotateCw, Search, Server, Trash2 } from 'lucide-react';
import { LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import Modal, { ConfirmDialog } from '../components/Modal.jsx';
import GenerateApiModal, { ApiDetails } from '../components/GenerateApiModal.jsx';
import KeyServersModal from '../components/KeyServersModal.jsx';
import { KeyServerTags } from '../components/UserDetailModal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { deleteKey, formatDate, formatDateTime, listKeys, listMyKeys, restoreKey, rotateKey } from '../services/mcpService.js';

const CONFIRM = {
  revoke: { title: 'Revoke gateway API?', label: 'Revoke', danger: true, text: 'will stop working immediately. Any client using this key will lose access. You can restore it later.' },
  restore: { title: 'Restore gateway API?', label: 'Restore', text: 'will work again with the same key value and its previous servers.' },
  rotate: { title: 'Rotate API key?', label: 'Rotate', danger: true, text: 'gets a new value. The current value stops working immediately, so update every client that uses it.' },
};

/** Server names of a key, for the details dialog (null = an admin key that reaches every server). */
const serverNames = (k) => (k.all_servers ? null : k.servers.filter((s) => !s.is_deleted).map((s) => s.server_name));

/**
 * Admins: GET /api/admin/keys (their keys and their users', revoked ones included) with revoke, restore, rotate and
 * server changes. Users: GET /api/user/keys (their live keys). Both create keys with POST /api/keys.
 */
export default function GatewayApis() {
  const { isAdmin, user } = useAuth();
  const notify = useToast();
  const { data, error, loading, reload } = useLoader(() => (isAdmin ? listKeys() : listMyKeys()), [isAdmin], []);
  const [query, setQuery] = useState('');
  const [owner, setOwner] = useState('');
  const [status, setStatus] = useState('');
  const [showGenerate, setShowGenerate] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [editingServers, setEditingServers] = useState(null);
  const [pending, setPending] = useState(null); // { key, action: 'revoke' | 'restore' | 'rotate' }
  const [rotated, setRotated] = useState(null);
  const [busy, setBusy] = useState(false);

  // User keys come without these fields: they are always the user's own, live, and never admin keys.
  const keys = useMemo(
    () => data.map((k) => ({ all_servers: false, is_deleted: false, user_id: user?.id, user_name: user?.user_name, ...k })),
    [data, user]
  );
  const owners = useMemo(() => {
    const m = new Map(keys.map((k) => [k.user_id, k.user_name]));
    return [...m.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1])));
  }, [keys]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return keys
      .filter((k) => !owner || String(k.user_id) === owner)
      .filter((k) => !status || (status === 'revoked' ? k.is_deleted : !k.is_deleted))
      .filter((k) => !q || k.key_name.toLowerCase().includes(q) || k.servers.some((s) => s.server_name.toLowerCase().includes(q)));
  }, [keys, owner, status, query]);
  const { sorted, sort, toggle } = useSort(filtered, 'created_at', 'desc');

  const confirm = async () => {
    const { key, action } = pending;
    setBusy(true);
    try {
      if (action === 'revoke') {
        await deleteKey(key.id);
        notify(`"${key.key_name}" revoked.`);
      } else if (action === 'restore') {
        await restoreKey(key.id);
        notify(`"${key.key_name}" restored.`);
      } else {
        const out = await rotateKey(key.id);
        setRotated({ ...out, names: serverNames(key) });
        notify(`"${key.key_name}" rotated. Copy the new key now.`);
      }
      setPending(null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
      reload();
    }
  };

  const activeCount = keys.filter((k) => !k.is_deleted).length;
  const cols = isAdmin ? 7 : 5;

  return (
    <div className="page">
      <PageHeader
        icon={KeyRound}
        title={isAdmin ? 'Gateway APIs' : 'My Gateway APIs'}
        subtitle={
          isAdmin
            ? 'Your API keys and your users’ keys. Clients send them to the gateway endpoint.'
            : 'Your API keys. Ask your admin to revoke, rotate or change the servers of a key.'
        }
        loading={loading}
        onRefresh={reload}
      />
      <LoadError error={error} onRetry={reload} />

      <div className="stat-row">
        <StatCard value={keys.length} label={<>{isAdmin ? 'Total' : 'Your'}<br />Gateway APIs</>} />
        <StatCard value={activeCount} tone="ok" label={<>Active<br />Keys</>} />
        {isAdmin && <StatCard value={keys.length - activeCount} label={<>Revoked<br />Keys</>} />}
        <button className="add-tile" onClick={() => setShowGenerate(true)} title="Generate gateway API" aria-label="Generate gateway API">
          <Plus size={28} />
        </button>
      </div>

      <div className="card table-card">
        <div className="table-toolbar wrap">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by key or server name..." />
          </div>
          <div className="filters">
            {isAdmin && (
              <>
                <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="Owner">
                  <option value="">All owners</option>
                  {owners.map(([id, name]) => (
                    <option key={id} value={id}>{id === user?.id ? `${name} (you)` : name}</option>
                  ))}
                </select>
                <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
                  <option value="">Active and revoked</option>
                  <option value="active">Active</option>
                  <option value="revoked">Revoked</option>
                </select>
              </>
            )}
            <span className="muted">{sorted.length} keys</span>
          </div>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <SortHeader label="ID" field="id" sort={sort} onSort={toggle} />
                <SortHeader label="Name" field="key_name" sort={sort} onSort={toggle} />
                {isAdmin && <SortHeader label="Owner" field="user_name" sort={sort} onSort={toggle} />}
                <th>Servers</th>
                {isAdmin && <th>Status</th>}
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              <TableState
                loading={loading}
                empty={sorted.length === 0}
                cols={cols}
                emptyText={keys.length ? 'No keys match your filters' : 'No gateway APIs yet. Use + to generate one.'}
              />
              {sorted.map((k) => {
                const revoked = k.is_deleted;
                return (
                  <tr key={k.id} className={revoked ? 'is-dim' : ''}>
                    <td className="id-cell">{k.id}</td>
                    <td><strong>{k.key_name}</strong></td>
                    {isAdmin && (
                      <td>
                        {k.user_id === user?.id ? 'You' : k.user_name}
                        {k.owner_type === 'user' && k.user_id !== user?.id && <small className="muted"> · user</small>}
                      </td>
                    )}
                    <td><KeyServerTags apiKey={k} /></td>
                    {isAdmin && (
                      <td>
                        <span className={`status-pill ${revoked ? 'deleted' : 'active'}`} title={revoked ? `Revoked ${formatDateTime(k.deleted_at)}` : ''}>
                          {revoked ? 'Revoked' : 'Active'}
                        </span>
                      </td>
                    )}
                    <td className="nowrap">{formatDate(k.created_at)}</td>
                    <td className="center nowrap">
                      <button className="icon-btn" onClick={() => setViewing(k)} title="View client config">
                        <FileCode size={17} />
                      </button>
                      {isAdmin && !revoked && (
                        <>
                          {!k.all_servers && (
                            <button className="icon-btn" onClick={() => setEditingServers(k)} title="Edit servers">
                              <Server size={17} />
                            </button>
                          )}
                          <button className="icon-btn" onClick={() => setPending({ key: k, action: 'rotate' })} title="Rotate key">
                            <RotateCw size={17} />
                          </button>
                          <button className="icon-btn danger-hover" onClick={() => setPending({ key: k, action: 'revoke' })} title="Revoke key">
                            <Trash2 size={17} />
                          </button>
                        </>
                      )}
                      {isAdmin && revoked && (
                        <button className="icon-btn" onClick={() => setPending({ key: k, action: 'restore' })} title="Restore key">
                          <RotateCcw size={17} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {showGenerate && (
        <GenerateApiModal
          onClose={() => setShowGenerate(false)}
          onGenerated={(k) => {
            notify(`"${k.key_name}" generated.`);
            reload();
          }}
        />
      )}

      {editingServers && (
        <KeyServersModal
          apiKey={editingServers}
          onClose={() => setEditingServers(null)}
          onSaved={(k) => {
            notify(`Servers of "${k.key_name}" updated.`);
            setEditingServers(null);
            reload();
          }}
        />
      )}

      {viewing && (
        <Modal title={viewing.key_name} subtitle="Gateway API details" icon={<KeyRound size={20} />} onClose={() => setViewing(null)} width={600}>
          <ApiDetails name={viewing.key_name} servers={serverNames(viewing)} />
          <div className="modal-actions">
            <button className="btn btn-primary" onClick={() => setViewing(null)}>Close</button>
          </div>
        </Modal>
      )}

      {rotated && (
        <Modal title="Key rotated" subtitle={rotated.key_name} icon={<KeyRound size={20} />} onClose={() => setRotated(null)} width={600}>
          <ApiDetails name={rotated.key_name} apiKey={rotated.api_key} servers={rotated.names} />
          <div className="modal-actions">
            <button className="btn btn-primary" onClick={() => setRotated(null)}>Done</button>
          </div>
        </Modal>
      )}

      {pending && (
        <ConfirmDialog
          title={CONFIRM[pending.action].title}
          message={
            <>
              <strong>{pending.key.key_name}</strong> {CONFIRM[pending.action].text}
            </>
          }
          confirmLabel={CONFIRM[pending.action].label}
          danger={CONFIRM[pending.action].danger}
          busy={busy}
          onConfirm={confirm}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}
