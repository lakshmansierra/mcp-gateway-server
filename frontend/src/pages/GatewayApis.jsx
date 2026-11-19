import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileCode, KeyRound, RefreshCw, Trash2 } from 'lucide-react';
import KeyCell from '../components/KeyCell.jsx';
import Modal, { ConfirmDialog } from '../components/Modal.jsx';
import { ApiDetails, CopyButton } from '../components/GenerateApiModal.jsx';
import { formatDate, listAllServers, listGatewayApis, revokeGatewayApi } from '../services/mcpService.js';

export default function GatewayApis() {
  const [apis, setApis] = useState([]);
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState(null);
  const [toRevoke, setToRevoke] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [a, s] = await Promise.all([listGatewayApis(), listAllServers()]);
    setApis([...a].sort((x, y) => y.createdAt.localeCompare(x.createdAt)));
    setServers(s);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Current state of each server behind an API: active, inactive, or removed.
  const serverState = (id) => {
    const s = servers.find((x) => x.id === id);
    if (!s || s.deletedAt) return 'removed';
    return s.status;
  };

  const confirmRevoke = async () => {
    setBusy(true);
    await revokeGatewayApi(toRevoke.id);
    setBusy(false);
    setToRevoke(null);
    load();
  };

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title">
          <div className="icon-tile">
            <KeyRound size={20} />
          </div>
          <div>
            <h1>My Gateway APIs</h1>
            <p className="muted">
              Endpoints generated from your selected MCP servers. <Link to="/mcp-servers" className="link">Generate a new one</Link>
            </p>
          </div>
        </div>
        <button className="btn btn-outline" onClick={load}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      <div className="card table-card">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Servers</th>
                <th>Endpoint</th>
                <th>API Key</th>
                <th>Created Date</th>
                <th className="center">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && apis.length === 0 ? (
                <tr><td colSpan={6} className="empty">Loading...</td></tr>
              ) : apis.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty">
                    No gateway APIs yet. Select servers on the <Link to="/mcp-servers" className="link">MCP Servers</Link> page to generate one.
                  </td>
                </tr>
              ) : (
                apis.map((a) => (
                  <tr key={a.id}>
                    <td><strong>{a.name}</strong></td>
                    <td>
                      <div className="tag-list">
                        {a.serverIds.map((id, i) => {
                          const state = serverState(id);
                          return (
                            <span
                              key={id}
                              className={`tag ${state !== 'active' ? 'tag-warn' : ''}`}
                              title={state === 'active' ? undefined : `This server is ${state}`}
                            >
                              {a.serverNames[i]}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                    <td>
                      <div className="key-cell">
                        <code className="key-value">{a.endpoint}</code>
                        <CopyButton text={a.endpoint} label="Copy endpoint" />
                      </div>
                    </td>
                    <td><KeyCell value={a.apiKey} /></td>
                    <td className="nowrap">{formatDate(a.createdAt)}</td>
                    <td className="center nowrap">
                      <button className="icon-btn" onClick={() => setViewing(a)} title="View client config">
                        <FileCode size={17} />
                      </button>
                      <button className="icon-btn danger-hover" onClick={() => setToRevoke(a)} title="Revoke API">
                        <Trash2 size={17} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {viewing && (
        <Modal title={viewing.name} subtitle="Gateway API details" icon={<KeyRound size={20} />} onClose={() => setViewing(null)} width={600}>
          <ApiDetails api={viewing} />
          <div className="modal-actions">
            <button className="btn btn-primary" onClick={() => setViewing(null)}>Close</button>
          </div>
        </Modal>
      )}

      {toRevoke && (
        <ConfirmDialog
          title="Revoke gateway API?"
          message={
            <>
              <strong>{toRevoke.name}</strong> will stop working immediately. Any client using this endpoint or key will lose access.
            </>
          }
          confirmLabel="Revoke"
          danger
          busy={busy}
          onConfirm={confirmRevoke}
          onClose={() => setToRevoke(null)}
        />
      )}
    </div>
  );
}
