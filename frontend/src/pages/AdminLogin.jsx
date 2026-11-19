import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Eye, EyeOff, Shield } from 'lucide-react';
import Logo from '../components/Logo.jsx';
import { useAuth } from '../context/AuthContext.jsx';

export default function AdminLogin() {
  const navigate = useNavigate();
  const { loginAdmin } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Please enter your username and password.');
      return;
    }
    setBusy(true);
    setError('');
    const ok = await loginAdmin(username.trim(), password);
    setBusy(false);
    if (ok) navigate('/dashboard');
    else setError('Invalid username or password.');
  };

  return (
    <div className="auth-page">
      <header className="auth-header">
        <Logo size={40} large />
      </header>

      <form className="card login-card" onSubmit={submit}>
        <button type="button" className="link-back" onClick={() => navigate('/')}>
          <ArrowLeft size={16} /> Back
        </button>

        <div className="login-title">
          <div className="icon-tile">
            <Shield size={22} strokeWidth={1.75} />
          </div>
          <div>
            <h3>Admin Login</h3>
            <p className="muted">Enter your credentials to continue</p>
          </div>
        </div>

        <label className="field">
          <span>Username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Enter username" autoComplete="username" autoFocus />
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
    </div>
  );
}
