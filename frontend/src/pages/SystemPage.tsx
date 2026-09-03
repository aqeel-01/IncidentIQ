import { Link } from "react-router-dom";

import { getHealth, getReadiness } from "@/api/health";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { useAsync } from "@/hooks/useAsync";
import { paths } from "@/routes/paths";

export function SystemPage() {
  const health = useAsync((signal) => getHealth(signal), []);
  const readiness = useAsync((signal) => getReadiness(signal), []);

  return (
    <section className="page">
      <div className="page__intro">
        <p className="eyebrow">System</p>
        <h1>Backend status</h1>
        <p className="lede">
          Liveness and readiness of the IncidentIQ API this dashboard talks to.
        </p>
      </div>

      <div className="card-grid">
        <article className="panel">
          <h2>Health</h2>
          {health.status === "loading" ? (
            <LoadingState label="Checking API health…" />
          ) : null}
          {health.status === "error" ? (
            <ErrorState
              title="API unreachable"
              message={health.error}
              onRetry={health.reload}
            />
          ) : null}
          {health.status === "success" ? (
            <dl className="meta-list">
              <div>
                <dt>Status</dt>
                <dd className="mono">{health.data.status}</dd>
              </div>
              <div>
                <dt>Service</dt>
                <dd className="mono">{health.data.service}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd className="mono">{health.data.version}</dd>
              </div>
              <div>
                <dt>Environment</dt>
                <dd className="mono">{health.data.environment}</dd>
              </div>
            </dl>
          ) : null}
        </article>

        <article className="panel">
          <h2>Readiness</h2>
          {readiness.status === "loading" ? (
            <LoadingState label="Checking dependencies…" />
          ) : null}
          {readiness.status === "error" ? (
            <ErrorState
              title="Readiness check failed"
              message={readiness.error}
              onRetry={readiness.reload}
            />
          ) : null}
          {readiness.status === "success" ? (
            <dl className="meta-list">
              <div>
                <dt>Overall</dt>
                <dd className="mono">{readiness.data.status}</dd>
              </div>
              {Object.entries(readiness.data.checks).map(([name, check]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd className="mono">
                    {typeof check.status === "string"
                      ? check.status
                      : JSON.stringify(check)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </article>
      </div>

      <div className="button-row">
        <Link className="button" to={paths.incidents}>
          Go to dashboard
        </Link>
      </div>
    </section>
  );
}
