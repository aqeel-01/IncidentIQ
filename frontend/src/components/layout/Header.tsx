import { NavLink } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { paths } from "@/routes/paths";

export function Header() {
  const auth = useAuth();

  return (
    <header className="app-header">
      <div className="app-header__brand">
        <NavLink to={paths.home} className="brand-mark">
          IncidentIQ
        </NavLink>
        <span className="brand-tag">investigation console</span>
      </div>

        <nav className="app-header__nav" aria-label="Primary">
          <NavLink to={paths.incidents} end>
            Dashboard
          </NavLink>
          <NavLink to={paths.system}>System</NavLink>
        </nav>

      <div className="app-header__session">
        {auth.isAuthenticated ? (
          <>
            <span className="mono">{auth.user?.displayName}</span>
            <button type="button" className="button button--ghost" onClick={auth.signOut}>
              Sign out
            </button>
          </>
        ) : (
          <NavLink to={paths.login} className="button button--ghost">
            Sign in
          </NavLink>
        )}
      </div>
    </header>
  );
}
