import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { bootstrap, login, toAuthUser } from "@/api/auth";
import { getErrorMessage } from "@/api/errors";
import { useAuth } from "@/auth/AuthContext";
import { paths } from "@/routes/paths";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const [orgName, setOrgName] = useState("Acme");
  const [orgSlug, setOrgSlug] = useState("acme");
  const [projectName, setProjectName] = useState("Payments");
  const [projectSlug, setProjectSlug] = useState("payments");
  const [fullName, setFullName] = useState("");

  const from =
    (location.state as { from?: string } | null)?.from ?? paths.home;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const result = await login(email.trim(), password);
      auth.signIn({
        accessToken: result.access_token,
        user: toAuthUser(result.user),
      });
      navigate(from, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, "Could not sign in."));
    } finally {
      setPending(false);
    }
  }

  async function onBootstrap(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const result = await bootstrap({
        organization_name: orgName.trim(),
        organization_slug: orgSlug.trim(),
        project_name: projectName.trim(),
        project_slug: projectSlug.trim(),
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
      });
      auth.signIn({
        accessToken: result.access_token,
        user: toAuthUser(result.user),
      });
      if (result.project_id) {
        window.localStorage.setItem(
          "incidentiq.project_id",
          String(result.project_id),
        );
      }
      navigate(from, { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, "Could not create the first admin."));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="page page--narrow">
      <div className="page__intro">
        <p className="eyebrow">Authentication</p>
        <h1>Sign in</h1>
        <p className="lede">
          Use your IncidentIQ account. Access is enforced by the API using
          organization, project, and role membership.
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
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        <div className="button-row">
          <button type="submit" className="button" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </button>
          <Link className="button button--ghost" to={paths.home}>
            Cancel
          </Link>
        </div>
      </form>

      <div className="panel">
        <button
          type="button"
          className="button button--ghost"
          onClick={() => setSetupOpen((open) => !open)}
        >
          {setupOpen ? "Hide first-time setup" : "First-time setup"}
        </button>
        {setupOpen ? (
          <form className="form" onSubmit={onBootstrap}>
            <p className="lede">
              Creates the first organization, project, and ADMIN user. Disabled
              once any user exists.
            </p>
            <label className="field">
              <span>Full name</span>
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Organization</span>
              <input
                value={orgName}
                onChange={(event) => setOrgName(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Organization slug</span>
              <input
                value={orgSlug}
                onChange={(event) => setOrgSlug(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Project</span>
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Project slug</span>
              <input
                value={projectSlug}
                onChange={(event) => setProjectSlug(event.target.value)}
                required
              />
            </label>
            <button type="submit" className="button" disabled={pending}>
              Create admin
            </button>
          </form>
        ) : null}
      </div>
    </section>
  );
}
