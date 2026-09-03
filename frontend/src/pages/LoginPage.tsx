import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { paths } from "@/routes/paths";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("dev@incidentiq.local");
  const [error, setError] = useState<string | null>(null);

  const from =
    (location.state as { from?: string } | null)?.from ?? paths.home;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!email.trim()) {
      setError("Email is required for the local session.");
      return;
    }

    // Backend auth is not implemented yet. This creates a local session so
    // Authorization headers and protected-route plumbing can be verified.
    auth.signIn({
      accessToken: `dev-token:${email.trim()}`,
      user: {
        id: "local-dev",
        email: email.trim(),
        displayName: email.trim().split("@")[0] || "Developer",
      },
    });
    navigate(from, { replace: true });
  }

  return (
    <section className="page page--narrow">
      <div className="page__intro">
        <p className="eyebrow">Authentication</p>
        <h1>Sign in</h1>
        <p className="lede">
          Auth-ready placeholder. Tokens are stored locally and attached as
          Bearer headers by the API client.
        </p>
      </div>

      <form className="panel form" onSubmit={onSubmit}>
        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="username"
          />
        </label>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="button-row">
          <button type="submit" className="button">
            Continue locally
          </button>
          <Link className="button button--ghost" to={paths.home}>
            Cancel
          </Link>
        </div>
      </form>
    </section>
  );
}
