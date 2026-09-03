import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "@/auth/AuthContext";
import { paths } from "@/routes/paths";
import { LoadingState } from "@/components/feedback/LoadingState";

type RequireAuthProps = {
  children: ReactNode;
  /**
   * When false, allow anonymous access while still mounting the auth shell.
   * Useful until backend authentication is enabled.
   */
  enabled?: boolean;
};

export function RequireAuth({ children, enabled = false }: RequireAuthProps) {
  const auth = useAuth();
  const location = useLocation();

  if (auth.status === "loading") {
    return <LoadingState label="Checking session…" />;
  }

  if (enabled && !auth.isAuthenticated) {
    return (
      <Navigate
        to={paths.login}
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  return children;
}
