import { History, Wrench } from 'lucide-react';
import Modal from './Modal.jsx';
import { LoadError } from './Common.jsx';
import { CopyButton } from './GenerateApiModal.jsx';
import { useLoader } from '../hooks/useLoader.js';
import { formatDateTime, getToolChanges } from '../services/mcpService.js';

const json = (v) => (v === null || v === undefined ? 'none' : JSON.stringify(v, null, 2));

/** A tool's details: name to call, description and input schema. Works for admin and user tool objects. */
export function ToolDetailsModal({ tool, onClose, onHistory }) {
  return (
    <Modal title={tool.tool_name} subtitle={tool.server_name} icon={<Wrench size={20} />} onClose={onClose} width={640}>
      <div className="form">
        <div className="field">
          <span>Name to call through the gateway</span>
          <div className="key-cell">
            <code className="key-value">{tool.gateway_name}</code>
            <CopyButton text={tool.gateway_name} label="Copy tool name" />
          </div>
        </div>
        <div className="field">
          <span>Description</span>
          <p className="confirm-msg" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
            {tool.description?.trim() || 'No description'}
          </p>
        </div>
        <div className="field">
          <div className="field-label-row">
            <span>Input schema</span>
            <CopyButton text={json(tool.input_schema)} label="Copy schema" />
          </div>
          <pre className="code-block" style={{ maxHeight: 280, overflow: 'auto' }}>{json(tool.input_schema)}</pre>
        </div>
        <small className="field-hint">First seen {formatDateTime(tool.first_seen_at)}</small>
      </div>
      <div className="modal-actions">
        {onHistory && (
          <button className="btn btn-outline" onClick={onHistory}>
            <History size={16} /> History
          </button>
        )}
        <button className="btn btn-primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}

const CHANGE_TAG = { added: 'tag-ok', removed: 'tag-danger', changed: '' };

/** GET /api/admin/tools/{id}/changes: what the server changed about this tool over time (admin only). */
export function ToolHistoryModal({ tool, onClose }) {
  const { data: changes, error, loading, reload } = useLoader(() => getToolChanges(tool.id), [tool.id], []);

  return (
    <Modal title={`History of ${tool.tool_name}`} subtitle={tool.server_name} icon={<History size={20} />} onClose={onClose} width={720}>
      <LoadError error={error} onRetry={reload} />
      {loading && changes.length === 0 ? (
        <p className="empty">Loading...</p>
      ) : changes.length === 0 ? (
        <p className="empty">No changes recorded</p>
      ) : (
        <ul className="timeline">
          {changes.map((c) => (
            <li key={c.id}>
              <div className="timeline-head">
                <span className={`tag ${CHANGE_TAG[c.change_type] ?? ''}`}>{c.change_type}</span>
                <span className="muted">{formatDateTime(c.changed_at)}</span>
              </div>
              {c.change_type === 'changed' ? (
                <div className="diff-cols">
                  <div>
                    <small>Before</small>
                    <pre className="code-block">{json(c.old_value)}</pre>
                  </div>
                  <div>
                    <small>After</small>
                    <pre className="code-block">{json(c.new_value)}</pre>
                  </div>
                </div>
              ) : (
                <pre className="code-block">{json(c.change_type === 'removed' ? c.old_value : c.new_value)}</pre>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="modal-actions">
        <button className="btn btn-primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
