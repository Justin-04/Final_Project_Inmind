import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, clearAuth, getAuth, registerUnauthorizedHandler, setAuth, type AuthState, type Role } from '@/services/api';
import { toast } from 'sonner';

interface AuthContextValue {
  auth: AuthState | null;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, role: Role) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuthState] = useState<AuthState | null>(() => getAuth());

  const handleUnauthorized = useCallback(() => {
    setAuthState(null);
    toast.error('Session expired. Please sign in again.');
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(handleUnauthorized);
  }, [handleUnauthorized]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password);
    const next: AuthState = {
      access_token: res.access_token,
      role: res.role,
      username: res.username,
    };
    setAuth(next);
    setAuthState(next);
    toast.success(`Welcome back, ${res.username}`);
  }, []);

  const register = useCallback(async (username: string, password: string, role: Role) => {
    const res = await api.register(username, password, role);
    const next: AuthState = {
      access_token: res.access_token,
      role: res.role,
      username: res.username,
    };
    setAuth(next);
    setAuthState(next);
    toast.success('Account created successfully');
  }, []);

  const logout = useCallback(() => {
    clearAuth();
    setAuthState(null);
    toast.success('Signed out');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ auth, login, register, logout }),
    [auth, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
