import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

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
  /**
   * Placeholder sign-in until backend auth lands.
   * Stores a session token so the API client can attach Authorization headers.
   */
  signIn: (session: AuthSession) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function readInitialSession(): AuthSession | null {
  const token = getAccessToken();
  if (!token) {
    return null;
  }

  // Auth is not implemented on the backend yet. Keep a lightweight local
  // session so protected routes and the API client stay auth-ready.
  return {
    accessToken: token,
    user: {
      id: "local-dev",
      email: "dev@incidentiq.local",
      displayName: "Local Developer",
    },
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(readInitialSession);

  const signIn = useCallback((next: AuthSession) => {
    setAccessToken(next.accessToken);
    setSession(next);
  }, []);

  const signOut = useCallback(() => {
    clearAccessToken();
    setSession(null);
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    const status: AuthStatus = session ? "authenticated" : "anonymous";
    return {
      status,
      user: session?.user ?? null,
      accessToken: session?.accessToken ?? null,
      isAuthenticated: status === "authenticated",
      signIn,
      signOut,
    };
  }, [session, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
