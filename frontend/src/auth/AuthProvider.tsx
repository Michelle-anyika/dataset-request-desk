import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, refreshSession, setAccessToken, setSessionExpiredHandler } from "../api/client";
import type { LoginResponse, User } from "../api/types";

type Status = "loading" | "signed-out" | "signed-in";

/** Why there is no session: the user signed out, or it expired (or never existed, on first load). */
type EndReason = "signed-out" | "expired" | null;

interface Auth {
  status: Status;
  endReason: EndReason;
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
  const [endReason, setEndReason] = useState<EndReason>(null);
  // Set once a sign-in or sign-out decides the session, so the start-up check can't overrule it.
  const decided = useRef(false);

  const end = useCallback((reason: Exclude<EndReason, null>) => {
    decided.current = true;
    setEndReason(reason);
    setAccessToken(null);
    queryClient.clear(); // nothing from this user's session stays in memory
    setUser(null);
    setStatus("signed-out");
  }, [queryClient]);

  // On load, the HttpOnly refresh cookie (if still valid) restores the session without asking again.
  useEffect(() => {
    setSessionExpiredHandler(() => end("expired"));
    let active = true;
    void (async () => {
      const restored = (await refreshSession()) && (await api<User>("/api/auth/me/").catch(() => null));
      // Only while nothing else has decided: someone who signed in before this answer came back (a fast typist,
      // a password manager) must not be signed out by a "no session" that describes the moment before.
      if (!active || decided.current) return;
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
    decided.current = true;
    setAccessToken(session.access);
    setEndReason(null);
    setUser(session.user);
    setStatus("signed-in");
    return session.user;
  }, []);

  const signOut = useCallback(async () => {
    // The refresh cookie identifies the session; the server ends it and clears the cookie.
    await api("/api/auth/logout/", { method: "POST", anonymous: true }).catch(() => undefined);
    end("signed-out");
  }, [end]);

  const signOutEverywhere = useCallback(async () => {
    await api("/api/auth/logout-all/", { method: "POST" }).catch(() => undefined);
    end("signed-out");
  }, [end]);

  const value = useMemo(
    () => ({ status, endReason, user, signIn, signOut, signOutEverywhere }),
    [status, endReason, user, signIn, signOut, signOutEverywhere],
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
