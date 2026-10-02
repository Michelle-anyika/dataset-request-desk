import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, refreshSession, setAccessToken, setSessionExpiredHandler } from "../api/client";
import type { LoginResponse, User } from "../api/types";

type Status = "loading" | "signed-out" | "signed-in";

interface Auth {
  status: Status;
  user: User | null;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
  signOutEverywhere: () => Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  const end = useCallback(() => {
    setAccessToken(null);
    queryClient.clear(); // nothing from this user's session stays in memory
    setUser(null);
    setStatus("signed-out");
  }, [queryClient]);

  // On load, the HttpOnly refresh cookie (if still valid) restores the session without asking again.
  useEffect(() => {
    setSessionExpiredHandler(end);
    let active = true;
    void (async () => {
      const restored = (await refreshSession()) && (await api<User>("/api/auth/me/").catch(() => null));
      if (!active) return;
      if (restored) {
        setUser(restored);
        setStatus("signed-in");
      } else {
        setStatus("signed-out");
      }
    })();
    return () => {
      active = false;
    };
  }, [end]);

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await api<LoginResponse>("/api/auth/login/", {
      method: "POST",
      body: { email, password },
      anonymous: true,
    });
    setAccessToken(session.access);
    setUser(session.user);
    setStatus("signed-in");
    return session.user;
  }, []);

  const signOut = useCallback(async () => {
    // The refresh cookie identifies the session; the server ends it and clears the cookie.
    await api("/api/auth/logout/", { method: "POST", anonymous: true }).catch(() => undefined);
    end();
  }, [end]);

  const signOutEverywhere = useCallback(async () => {
    await api("/api/auth/logout-all/", { method: "POST" }).catch(() => undefined);
    end();
  }, [end]);

  const value = useMemo(
    () => ({ status, user, signIn, signOut, signOutEverywhere }),
    [status, user, signIn, signOut, signOutEverywhere],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <AuthProvider>");
  return auth;
}

/** The signed-in user. Only for pages behind <RequireAuth>, where there always is one. */
export function useUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("useUser needs a signed-in user");
  return user;
}
