import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { fetchCurrentUser, toAuthUser } from "@/api/auth";
import { isUnauthorized } from "@/api/errors";
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from "@/auth/tokenStorage";
import type { AuthSession, AuthStatus, AuthUser } from "@/auth/types";

type AuthContextValue = {
  status: AuthStatus;
  user: AuthUser | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  signIn: (session: AuthSession) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const signIn = useCallback((next: AuthSession) => {
    setAccessToken(next.accessToken);
    setSession(next);
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(() => {
    clearAccessToken();
    setSession(null);
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setStatus("anonymous");
      return;
    }

    const controller = new AbortController();
    fetchCurrentUser(controller.signal)
      .then((payload) => {
        setSession({
          accessToken: token,
          user: toAuthUser(payload),
        });
        setStatus("authenticated");
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (isUnauthorized(error)) {
          clearAccessToken();
        }
        setSession(null);
        setStatus("anonymous");
      });

    return () => controller.abort();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user: session?.user ?? null,
      accessToken: session?.accessToken ?? null,
      isAuthenticated: status === "authenticated",
      signIn,
      signOut,
    }),
    [session, signIn, signOut, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
