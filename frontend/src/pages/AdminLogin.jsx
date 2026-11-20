import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Eye, EyeOff, Shield, User } from 'lucide-react';
import AuthShell from '../components/AuthShell.jsx';
import { homeFor, useAuth } from '../context/AuthContext.jsx';

/** Login page for both account types: mode 'admin' -> POST /api/admin/login, 'user' -> POST /api/user/login. */
export default function AdminLogin({ mode = 'admin' }) {
  const navigate = useNavigate();
  const { login, notice } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const isAdmin = mode === 'admin';

  const submit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please enter your username and password.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const user = await login(mode, username.trim(), password);
      navigate(homeFor(user.type === 'admin' ? 'admin' : 'user'));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <form className="auth-panel login-card" onSubmit={submit}>
        <button type="button" className="link-back" onClick={() => navigate('/')}>
          <ArrowLeft size={16} /> Back
        </button>

        <div className="login-title">
          <div className={`icon-tile ${isAdmin ? '' : 'neutral'}`}>
            {isAdmin ? <Shield size={22} strokeWidth={1.75} /> : <User size={22} strokeWidth={1.75} />}
          </div>
          <div>
            <h3>{isAdmin ? 'Admin Login' : 'User Login'}</h3>
            <p className="muted">Enter your credentials to continue</p>
          </div>
        </div>

        {notice && !error && <div className="alert-info">{notice}</div>}

        <label className="field">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Enter username" autoComplete="username" maxLength={100} autoFocus />
        </label>

        <label className="field">
          <span>Password</span>
          <div className="input-with-btn">
            <input
              type={showPw ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              autoComplete="current-password"
              maxLength={200}
            />
            <button type="button" className="icon-btn subtle" onClick={() => setShowPw((s) => !s)} aria-label="Toggle password visibility">
              {showPw ? <Eye size={17} /> : <EyeOff size={17} />}
            </button>
          </div>
        </label>

        {error && <div className="alert-error">{error}</div>}

        <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={busy}>
          {busy ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </AuthShell>
  );
}
