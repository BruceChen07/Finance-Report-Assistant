/**
 * Auth provider:
 * - Stores JWT in localStorage
 * - Provides login/logout and /api/auth/me bootstrap
 */
import React, { PropsWithChildren, createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiFetch, clearToken, getToken, setToken } from "../../utils/api-client";

type AuthCtx = {
  token: string | null;
  username: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [username, setUsername] = useState<string | null>(null);

  const logout = () => {
    clearToken();
    setTokenState(null);
    setUsername(null);
  };

  const login = async (u: string, p: string) => {
    const res = await apiFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as { access_token: string };
    setToken(data.access_token);
    setTokenState(data.access_token);
  };

  useEffect(() => {
    const run = async () => {
      if (!token) return;
      const res = await apiFetch("/api/auth/me");
      if (res.ok) {
        const d = (await res.json()) as { username: string };
        setUsername(d.username);
      } else {
        logout();
      }
    };
    run();
  }, [token]);

  const value = useMemo(() => ({ token, username, login, logout }), [token, username]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("AuthProvider missing");
  return v;
}