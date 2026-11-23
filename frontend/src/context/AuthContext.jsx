import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { configureApi } from '../services/api.js';
import * as svc from '../services/mcpService.js';

const STORAGE_KEY = 'mcp_gateway_session';

const AuthContext = createContext(null);

/** Session: { token, expiresAt (ms), user: UserOut } or null. */
function loadSession() {
  try {
    const s = JSON.parse(sessionStorage.getItem(STORAGE_KEY));
    if (s?.token && s.expiresAt > Date.now()) return s;
  } catch {
    /* ignore */
  }
  return null;
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSession);
  const [notice, setNotice] = useState('');
  const sessionRef = useRef(session);
  sessionRef.current = session;

  const persist = useCallback((next) => {
    sessionRef.current = next;
    setSession(next);
    try {
      if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable: session lives in memory only */
    }
  }, []);

  const endSession = useCallback(
    (message = '') => {
      persist(null);
      setNotice(message);
    },
    [persist]
  );

  // Configure synchronously so requests made by child effects on the first render already carry the token.
  configureApi({
    session: () => sessionRef.current,
    unauthorized: (message) => sessionRef.current && endSession(message),
  });

  // On page load, refresh the stored account from GET /api/me (a 401 there ends the session via the API client).
  useEffect(() => {
    if (!sessionRef.current) return;
    svc
      .getMe()
      .then((user) => sessionRef.current && persist({ ...sessionRef.current, user }))
      .catch(() => {
        /* offline or 401: the API client already handled it */
      });
  }, [persist]);

  // End the session when the token expires.
  useEffect(() => {
    if (!session) return undefined;
    const ms = session.expiresAt - Date.now();
    const t = setTimeout(() => endSession('Your session has expired. Please sign in again.'), Math.max(0, ms));
    return () => clearTimeout(t);
  }, [session, endSession]);

  /** kind: 'admin' | 'user'. Throws ApiError on bad credentials. */
  const login = async (kind, username, password) => {
    const out = await svc.login(kind, username, password);
    persist({ token: out.access_token, expiresAt: Date.now() + out.expires_in * 1000, user: out.user });
    setNotice('');
    return out.user;
  };

  const logout = async () => {
    try {
      await svc.logout();
    } catch {
      /* the token is dropped locally either way */
    }
    endSession();
  };

  const logoutAll = async () => {
    await svc.logoutAll();
    endSession('You have been logged out on every device.');
  };

  /** The backend logs the account out everywhere after a password change. */
  const changePassword = async (oldPassword, newPassword) => {
    await svc.changePassword(oldPassword, newPassword);
    endSession('Password changed. Sign in with your new password.');
  };

  const user = session?.user || null;
  const role = user ? (user.type === 'admin' ? 'admin' : 'user') : null;

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        username: user?.user_name || null,
        isAdmin: role === 'admin',
        notice,
        clearNotice: () => setNotice(''),
        login,
        logout,
        logoutAll,
        changePassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

/** Where each role lands after signing in. */
export const homeFor = (role) => (role === 'admin' ? '/dashboard' : '/gateway-apis');
