import { useCallback, useEffect, useState } from 'react';
import { FileCode, KeyRound, Plus, RefreshCw, RotateCcw, RotateCw, Server, Settings2, Trash2 } from 'lucide-react';
import Modal, { ConfirmDialog } from '../components/Modal.jsx';
import GenerateApiModal, { ApiDetails } from '../components/GenerateApiModal.jsx';
import KeyServersModal from '../components/KeyServersModal.jsx';
import ManageKeyModal from '../components/ManageKeyModal.jsx';
import { useToast } from '../components/Toast.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { deleteKey, formatDate, listAllServers, listKeys, listUsers, restoreKey, rotateKey } from '../services/mcpService.js';

const CONFIRM = {
  revoke: { title: 'Revoke gateway API?', label: 'Revoke', danger: true, text: 'will stop working immediately. Any client using this key will lose access. You can restore it later.' },
  restore: { title: 'Restore gateway API?', label: 'Restore', text: 'will work again with the same key value and its previous servers.' },
  rotate: { title: 'Rotate API key?', label: 'Rotate', danger: true, text: 'gets a new value. The current value stops working immediately, so update every client that uses it.' },
};

export default function GatewayApis() {
  const { isAdmin, user } = useAuth();
  const notify = useToast();
  const [keys, setKeys] = useState([]);
  const [servers, setServers] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showGenerate, setShowGenerate] = useState(false);
  const [showManage, setShowManage] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [editingServers, setEditingServers] = useState(null);
  const [pending, setPending] = useState(null); // { key, action: 'revoke' | 'restore' | 'rotate' }
  const [rotated, setRotated] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setKeys([...listKeys()].sort((x, y) => String(y.created_at).localeCompare(String(x.created_at))));
    setServers(listAllServers());
    setUsers(listUsers());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const serverLabel = (id) => {
    const s = servers.find((x) => x.id === id);
    return s ? s.server_name : `#${id}`;
  };

  // State of a server behind a key, when this browser knows it: active, inactive or removed.
  const serverState = (id) => {
    const s = servers.find((x) => x.id === id);
    if (!s) return null;
    if (s.deleted_at) return 'removed';
    return s.enabled ? 'active' : 'inactive';
  };

  const ownerLabel = (k) => {
    if (k.user_id === user?.id) return 'You';
    const u = users.find((x) => x.id === k.user_id);
    return u ? u.user_name : k.user_id ? `User #${k.user_id}` : '-';
  };

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
        setRotated(await rotateKey(key.id));
        notify(`"${key.key_name}" rotated. Copy the new key now.`);
      }
      setPending(null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
      load();
    }
  };

  const activeCount = keys.filter((k) => !k.deleted_at).length;
  const colCount = isAdmin ? 7 : 6;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">
          <div className="icon-tile">
            <KeyRound size={20} />
          </div>
          <div>
            <h1>{isAdmin ? 'Gateway APIs' : 'My Gateway APIs'}</h1>
            <p className="muted">
              {isAdmin
                ? 'API keys created or managed from this browser. Clients send them to the gateway endpoint.'
                : 'Keys you generated in this browser. Ask your admin to revoke or change a key.'}
            </p>
          </div>
        </div>
        <div className="header-actions">
          {isAdmin && (
            <button className="btn btn-outline" onClick={() => setShowManage(true)}>
              <Settings2 size={16} /> Manage Key by ID
            </button>
          )}
          <button className="btn btn-outline" onClick={load}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      <div className="stat-row">
        <div className="card stat-card">
          <strong>{keys.length}</strong>
          <span>Total<br />Gateway APIs</span>
        </div>
        <div className="card stat-card">
          <strong className="ok">{activeCount}</strong>
          <span>Active<br />Keys</span>
        </div>
        <button className="add-tile" onClick={() => setShowGenerate(true)} title="Generate gateway API" aria-label="Generate gateway API">
          <Plus size={28} />
        </button>
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                {isAdmin && <th>Owner</th>}
                <th>Servers</th>
                <th>Status</th>
                <th>Created Date</th>
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && keys.length === 0 ? (
                <tr><td colSpan={colCount} className="empty">Loading...</td></tr>
              ) : keys.length === 0 ? (
                <tr>
                  <td colSpan={colCount} className="empty">
                    No gateway APIs yet. Use <strong>+</strong> to generate one.
                  </td>
                </tr>
              ) : (
                keys.map((k) => {
                  const revoked = !!k.deleted_at;
                  return (
                    <tr key={k.id}>
                      <td className="id-cell">{k.id}</td>
                      <td><strong>{k.key_name}</strong></td>
                      {isAdmin && <td>{ownerLabel(k)}</td>}
                      <td>
                        <div className="tag-list">
                          {k.all_servers ? (
                            <span className="tag">All servers</span>
                          ) : (
                            k.server_ids.map((id) => {
                              const state = serverState(id);
                              const warn = state && state !== 'active';
                              return (
                                <span key={id} className={`tag ${warn ? 'tag-warn' : ''}`} title={warn ? `This server is ${state}` : `Server #${id}`}>
                                  {serverLabel(id)}
                                </span>
                              );
                            })
                          )}
                        </div>
                      </td>
                      <td>
                        <span className={`status-pill ${revoked ? 'deleted' : 'active'}`}>{revoked ? 'Revoked' : 'Active'}</span>
                      </td>
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
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showGenerate && (
        <GenerateApiModal
          serverLabel={serverLabel}
          onClose={() => setShowGenerate(false)}
          onGenerated={(k) => {
            notify(`"${k.key_name}" generated.`);
            load();
          }}
        />
      )}

      {showManage && (
        <ManageKeyModal
          serverLabel={serverLabel}
          onClose={() => {
            setShowManage(false);
            load();
          }}
          onDone={(message) => {
            setShowManage(false);
            notify(message);
            load();
          }}
        />
      )}

      {editingServers && (
        <KeyServersModal
          apiKey={editingServers}
          servers={servers}
          onClose={() => setEditingServers(null)}
          onSaved={(k) => {
            notify(`Servers of "${k.key_name}" updated.`);
            setEditingServers(null);
            load();
          }}
        />
      )}

      {viewing && (
        <Modal title={viewing.key_name} subtitle="Gateway API details" icon={<KeyRound size={20} />} onClose={() => setViewing(null)} width={600}>
          <ApiDetails name={viewing.key_name} servers={viewing.all_servers ? null : viewing.server_ids.map(serverLabel)} />
          <div className="modal-actions">
            <button className="btn btn-primary" onClick={() => setViewing(null)}>Close</button>
          </div>
        </Modal>
      )}

      {rotated && (
        <Modal title="Key rotated" subtitle={rotated.key_name} icon={<KeyRound size={20} />} onClose={() => setRotated(null)} width={600}>
          <ApiDetails name={rotated.key_name} apiKey={rotated.api_key} servers={rotated.all_servers ? null : rotated.server_ids.map(serverLabel)} />
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
