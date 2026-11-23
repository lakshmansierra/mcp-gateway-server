import { useMemo, useState } from 'react';
import { Eye, KeyRound, Plus, RotateCcw, Search, Trash2, Users as UsersIcon } from 'lucide-react';
import { LoadError, PageHeader, StatCard, TableState } from '../components/Common.jsx';
import { ConfirmDialog } from '../components/Modal.jsx';
import UserDetailModal from '../components/UserDetailModal.jsx';
import SortHeader, { useSort } from '../components/SortHeader.jsx';
import { useToast } from '../components/Toast.jsx';
import { CreateUserModal, ResetPasswordModal } from '../components/UserModals.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { deleteUser, formatDate, formatDateTime, listUsers, restoreUser } from '../services/mcpService.js';

export default function Users() {
  const notify = useToast();
  const { data: users, error, loading, reload: load } = useLoader(listUsers, [], []);
  const [query, setQuery] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [resetting, setResetting] = useState(null);
  const [pending, setPending] = useState(null); // { user, action: 'delete' | 'restore' }
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState(null);

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
        notify(`"${user.user_name}" restored. Their API keys stay revoked until you restore them on Gateway APIs.`);
      }
      setPending(null);
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setBusy(false);
      load();
    }
  };

  const activeCount = users.filter((u) => !u.is_deleted).length;

  return (
    <div className="page">
      <PageHeader icon={UsersIcon} title="Users" subtitle="User accounts you created. Deleted users stay listed so you can restore them." loading={loading} onRefresh={load} />
      <LoadError error={error} onRetry={load} />

      <div className="stat-row">
        <StatCard value={users.length} label={<>Total<br />Users</>} />
        <StatCard value={activeCount} tone="ok" label={<>Active<br />Users</>} />
        <StatCard value={users.length - activeCount} label={<>Deleted<br />Users</>} />
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
                <SortHeader label="Keys" field="key_count" sort={sort} onSort={toggle} />
                <SortHeader label="Created Date" field="created_at" sort={sort} onSort={toggle} />
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              <TableState loading={loading} empty={sorted.length === 0} cols={6} emptyText={query ? 'No users match your search' : 'No users yet. Use + to create one.'} />
              {sorted.map((u) => {
                  const deleted = u.is_deleted;
                  return (
                    <tr key={u.id}>
                      <td className="id-cell">{u.id}</td>
                      <td>
                        <button className="btn-text" onClick={() => setViewing(u.id)}><strong>{u.user_name}</strong></button>
                      </td>
                      <td>
                        <span className={`status-pill ${deleted ? 'deleted' : 'active'}`} title={deleted ? `Deleted ${formatDateTime(u.deleted_at)}` : ''}>
                          {deleted ? 'Deleted' : 'Active'}
                        </span>
                      </td>
                      <td className="num">{u.key_count}</td>
                      <td className="nowrap">{formatDate(u.created_at)}</td>
                      <td className="center nowrap">
                        <button className="icon-btn" onClick={() => setViewing(u.id)} title="Details and keys">
                          <Eye size={17} />
                        </button>
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
                })}
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

      {viewing && <UserDetailModal userId={viewing} onClose={() => setViewing(null)} />}

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
