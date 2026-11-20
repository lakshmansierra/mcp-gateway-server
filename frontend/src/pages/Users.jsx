import { useCallback, useEffect, useMemo, useState } from 'react';
import { KeyRound, Plus, RefreshCw, RotateCcw, Search, Trash2, Users as UsersIcon } from 'lucide-react';
import { ConfirmDialog } from '../components/Modal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { CreateUserModal, ResetPasswordModal } from '../components/UserModals.jsx';
import { deleteUser, formatDate, listUsers, restoreUser } from '../services/mcpService.js';

export default function Users() {
  const notify = useToast();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [resetting, setResetting] = useState(null);
  const [pending, setPending] = useState(null); // { user, action: 'delete' | 'restore' }
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setUsers(listUsers());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? users.filter((u) => u.user_name.toLowerCase().includes(q)) : users;
  }, [users, query]);

  const { sorted, sort, toggle } = useSort(filtered, 'created_at', 'desc');

  const confirm = async () => {
    const { user, action } = pending;
    setBusy(true);
    try {
      if (action === 'delete') {
        const out = await deleteUser(user.id);
        const n = out.api_keys_revoked;
        notify(`"${user.user_name}" deleted. ${n} API key${n === 1 ? '' : 's'} revoked.`);
      } else {
        await restoreUser(user.id);
        notify(`"${user.user_name}" restored. Their API keys stay revoked until you restore them.`);
      }
      setPending(null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
      load();
    }
  };

  const activeCount = users.filter((u) => !u.deleted_at).length;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">
          <div className="icon-tile">
            <UsersIcon size={20} />
          </div>
          <div>
            <h1>Users</h1>
            <p className="muted">User accounts you created or changed from this browser</p>
          </div>
        </div>
        <button className="btn btn-outline" onClick={load}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      <div className="stat-row">
        <div className="card stat-card">
          <strong>{users.length}</strong>
          <span>Total<br />Users</span>
        </div>
        <div className="card stat-card">
          <strong className="ok">{activeCount}</strong>
          <span>Active<br />Users</span>
        </div>
        <button className="add-tile" onClick={() => setShowCreate(true)} title="Create user" aria-label="Create user">
          <Plus size={28} />
        </button>
      </div>

      <div className="card table-card">
        <div className="table-toolbar">
          <div className="search">
            <Search size={16} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by username..." />
          </div>
          <span className="muted">{filtered.length} users</span>
        </div>

        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <SortHeader label="ID" field="id" sort={sort} onSort={toggle} />
                <SortHeader label="Username" field="user_name" sort={sort} onSort={toggle} />
                <th>Status</th>
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && users.length === 0 ? (
                <tr><td colSpan={5} className="empty">Loading...</td></tr>
              ) : sorted.length === 0 ? (
                <tr><td colSpan={5} className="empty">{query ? 'No users match your search' : 'No users created from this browser yet'}</td></tr>
              ) : (
                sorted.map((u) => {
                  const deleted = !!u.deleted_at;
                  return (
                    <tr key={u.id}>
                      <td className="id-cell">{u.id}</td>
                      <td><strong>{u.user_name}</strong></td>
                      <td>
                        <span className={`status-pill ${deleted ? 'deleted' : 'active'}`}>{deleted ? 'Deleted' : 'Active'}</span>
                      </td>
                      <td className="nowrap">{formatDate(u.created_at)}</td>
                      <td className="center nowrap">
                        {deleted ? (
                          <button className="icon-btn" onClick={() => setPending({ user: u, action: 'restore' })} title="Restore user">
                            <RotateCcw size={17} />
                          </button>
                        ) : (
                          <>
                            <button className="icon-btn" onClick={() => setResetting(u)} title="Reset password">
                              <KeyRound size={17} />
                            </button>
                            <button className="icon-btn danger-hover" onClick={() => setPending({ user: u, action: 'delete' })} title="Delete user">
                              <Trash2 size={17} />
                            </button>
                          </>
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

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreated={(u) => {
            notify(`User "${u.user_name}" created.`);
            setShowCreate(false);
            load();
          }}
        />
      )}

      {resetting && (
        <ResetPasswordModal
          user={resetting}
          onClose={() => setResetting(null)}
          onDone={(u) => {
            notify(`Password of "${u.user_name}" reset.`);
            setResetting(null);
            load();
          }}
        />
      )}

      {pending && (
        <ConfirmDialog
          title={pending.action === 'delete' ? 'Delete user?' : 'Restore user?'}
          message={
            pending.action === 'delete' ? (
              <>
                <strong>{pending.user.user_name}</strong> will no longer be able to sign in, and all of their API keys will be revoked.
              </>
            ) : (
              <>
                <strong>{pending.user.user_name}</strong> will be able to sign in again. Their API keys stay revoked until you restore them.
              </>
            )
          }
          confirmLabel={pending.action === 'delete' ? 'Delete' : 'Restore'}
          danger={pending.action === 'delete'}
          busy={busy}
          onConfirm={confirm}
          onClose={() => setPending(null)}
        />
      )}
    </div>
  );
}
