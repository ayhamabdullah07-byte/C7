import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, getToken, setToken } from './api';
import { loadLang } from './i18n';

type User = any;

type Ctx = {
  user: User | null;
  loading: boolean;
  bootDone: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  setUserLocal: (u: User) => void;
};

const AuthCtx = createContext<Ctx>({} as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootDone, setBootDone] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      await setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await loadLang();
      const tk = await getToken();
      if (tk) await refresh();
      setBootDone(true);
    })();
  }, [refresh]);

  const signIn = async (email: string, password: string) => {
    setLoading(true);
    try {
      const r = await api.login(email, password);
      await setToken(r.token);
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  const signUp = async (email: string, password: string, name: string) => {
    setLoading(true);
    try {
      const r = await api.register(email, password, name);
      await setToken(r.token);
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    await setToken(null);
    setUser(null);
  };

  return (
    <AuthCtx.Provider
      value={{ user, loading, bootDone, signIn, signUp, signOut, refresh, setUserLocal: setUser }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}
