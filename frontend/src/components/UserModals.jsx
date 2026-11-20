import { useState } from 'react';
import { KeyRound, UserPlus } from 'lucide-react';
import Modal from './Modal.jsx';
import { createUser, MIN_PASSWORD, NAME_PATTERN, resetUserPassword } from '../services/mcpService.js';

function PasswordFields({ form, set, errors }) {
  return (
    <div className="field-row">
      <label className="field">
        <span>Password</span>
        <input type="password" value={form.password} onChange={set('password')} autoComplete="new-password" />
        {errors.password ? <em className="field-error">{errors.password}</em> : <small className="field-hint">At least {MIN_PASSWORD} characters</small>}
      </label>
      <label className="field">
        <span>Confirm password</span>
        <input type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" />
        {errors.confirm && <em className="field-error">{errors.confirm}</em>}
      </label>
    </div>
  );
}

function usePasswordForm(initial) {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});
  const set = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setErrors((er) => ({ ...er, [field]: undefined }));
  };
  const checkPassword = (er) => {
    if (form.password.length < MIN_PASSWORD) er.password = `At least ${MIN_PASSWORD} characters`;
    if (form.confirm !== form.password) er.confirm = 'Passwords do not match';
  };
  return { form, set, errors, setErrors, checkPassword };
}

/** POST /api/admin/users with RegisterRequest { user_name, password }. */
export function CreateUserModal({ onClose, onCreated }) {
  const { form, set, errors, setErrors, checkPassword } = usePasswordForm({ user_name: '', password: '', confirm: '' });
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    const er = {};
    const name = form.user_name.trim();
    if (name.length < 3) er.user_name = 'At least 3 characters';
    else if (name.length > 100) er.user_name = 'At most 100 characters';
    else if (!NAME_PATTERN.test(name)) er.user_name = 'Use only letters, digits, ".", "_" and "-"';
    checkPassword(er);
    setErrors(er);
    if (Object.keys(er).length) return;

    setBusy(true);
    setApiError('');
    try {
      onCreated(await createUser({ user_name: name, password: form.password }));
    } catch (err) {
      setApiError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Create User" subtitle="Users sign in with User Access and generate their own keys" icon={<UserPlus size={20} />} onClose={onClose}>
      <form onSubmit={submit} className="form" noValidate>
        <label className="field">
          <span>Username</span>
          <input value={form.user_name} onChange={set('user_name')} placeholder="e.g. jane.doe" maxLength={100} autoComplete="off" autoFocus />
          {errors.user_name && <em className="field-error">{errors.user_name}</em>}
        </label>
        <PasswordFields form={form} set={set} errors={errors} />

        {apiError && <div className="alert-error">{apiError}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Creating...' : 'Create User'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** PATCH /api/admin/users/{id}/password with PasswordReset { new_password }. */
export function ResetPasswordModal({ user, onClose, onDone }) {
  const { form, set, errors, setErrors, checkPassword } = usePasswordForm({ password: '', confirm: '' });
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    const er = {};
    checkPassword(er);
    setErrors(er);
    if (Object.keys(er).length) return;

    setBusy(true);
    setApiError('');
    try {
      onDone(await resetUserPassword(user.id, form.password));
    } catch (err) {
      setApiError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Reset Password" subtitle={user.user_name} icon={<KeyRound size={20} />} onClose={onClose}>
      <form onSubmit={submit} className="form" noValidate>
        <PasswordFields form={form} set={set} errors={errors} />
        {apiError && <div className="alert-error">{apiError}</div>}
        <div className="modal-actions">
          <button type="button" className="btn btn-outline" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Saving...' : 'Reset Password'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
