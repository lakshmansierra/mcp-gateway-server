import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut, Settings } from 'lucide-react';
import Modal from './Modal.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { MIN_PASSWORD } from '../services/mcpService.js';

/** The signed-in account: PATCH /api/me/password and POST /api/me/logout-all. */
export default function AccountModal({ onClose }) {
  const { isAdmin, changePassword, logoutAll } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ old: '', next: '', confirm: '' });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState('');
  const [busy, setBusy] = useState(''); // '' | 'password' | 'logout-all'

  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };

  const submit = async (e) => {
    e.preventDefault();
    const er = {};
    if (!form.old) er.old = 'Enter your current password';
    if (form.next.length < MIN_PASSWORD) er.next = `At least ${MIN_PASSWORD} characters`;
    else if (form.next === form.old) er.next = 'Must differ from the current password';
    if (form.confirm !== form.next) er.confirm = 'Passwords do not match';
    setErrors(er);
    if (Object.keys(er).length) return;

    setBusy('password');
    setApiError('');
    try {
      await changePassword(form.old, form.next);
      navigate(isAdmin ? '/login' : '/user-login');
    } catch (err) {
      setApiError(err.message);
      setBusy('');
    }
  };

  const signOutEverywhere = async () => {
    setBusy('logout-all');
    setApiError('');
    try {
      await logoutAll();
      navigate('/');
    } catch (err) {
      setApiError(err.message);
      setBusy('');
    }
  };

  return (
    <Modal title="Account" subtitle="Change your password or end your sessions" icon={<Settings size={20} />} onClose={onClose}>
      <form onSubmit={submit} className="form" noValidate>
        <label className="field">
          <span>Current password</span>
          <input type="password" value={form.old} onChange={set('old')} autoComplete="current-password" maxLength={200} autoFocus />
          {errors.old && <em className="field-error">{errors.old}</em>}
        </label>
        <div className="field-row">
          <label className="field">
            <span>New password</span>
            <input type="password" value={form.next} onChange={set('next')} autoComplete="new-password" />
            {errors.next && <em className="field-error">{errors.next}</em>}
          </label>
          <label className="field">
            <span>Confirm new password</span>
            <input type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" />
            {errors.confirm && <em className="field-error">{errors.confirm}</em>}
          </label>
        </div>
        <p className="field-hint">Changing your password signs you out on every device.</p>

        {apiError && <div className="alert-error">{apiError}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={signOutEverywhere} disabled={!!busy} style={{ marginRight: 'auto' }}>
            <LogOut size={16} /> {busy === 'logout-all' ? 'Logging out...' : 'Log out all devices'}
          </button>
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={!!busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!!busy}>
            {busy === 'password' ? 'Saving...' : 'Change Password'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
