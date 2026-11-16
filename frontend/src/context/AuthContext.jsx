import { createContext, useContext, useState } from 'react';

const STORAGE_KEY = 'mcp_gateway_session';

// Demo credentials: replace with a real auth call (e.g. XSUAA / OAuth) when the backend is ready.
const DEMO_ADMIN = { username: 'admin', password: 'admin123' };

const AuthContext = createContext(null);

function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || { role: null, username: null };
  } catch {
    return { role: null, username: null };
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(loadSession);

  const persist = (next) => {
    setSession(next);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* storage unavailable: session lives in memory only */
    }
  };

  const loginAdmin = async (username, password) => {
    if (username === DEMO_ADMIN.username && password === DEMO_ADMIN.password) {
      persist({ role: 'admin', username });
      return true;
    }
    return false;
  };

  const continueAsUser = () => persist({ role: 'user', username: 'Guest' });

  const logout = () => {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    setSession({ role: null, username: null });
  };

  return (
    <AuthContext.Provider
      value={{
        role: session.role,
        username: session.username,
        isAdmin: session.role === 'admin',
        loginAdmin,
        continueAsUser,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
