import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getErrorMessage } from "@/api/errors";
import { getIncidentEvidence } from "@/api/evidence";
import { getIncident } from "@/api/incidents";
import {
  getInvestigation,
  getLatestIncidentInvestigation,
  startInvestigation,
} from "@/api/investigations";
import { getLatestIncidentRCA } from "@/api/rca";
import { getIncidentTimeline } from "@/api/timeline";
import type { Investigation, TimelineEntry } from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { SeverityBadge, StatusBadge } from "@/components/incidents/Badges";
import { EvidenceSection } from "@/components/investigation/EvidenceSection";
import { InvestigationProgress } from "@/components/investigation/InvestigationProgress";
import {
  InvestigationSection,
  SectionEmpty,
} from "@/components/investigation/InvestigationSection";
import {
  HypothesesSection,
  RCASection,
  VerificationSection,
} from "@/components/investigation/RCASections";
import {
  DeploymentsSection,
  ErrorsSection,
  MetricsSection,
} from "@/components/investigation/SignalSections";
import { TimelineSection } from "@/components/investigation/TimelineSection";
import { useAsync } from "@/hooks/useAsync";
import { paths } from "@/routes/paths";
import {
  formatDateTime,
  formatNumber,
  formatRelativeTime,
} from "@/utils/format";

const SECTION_LINKS = [
  ["summary", "Summary"],
  ["timeline", "Timeline"],
  ["errors", "Errors"],
  ["metrics", "Metrics"],
  ["deployments", "Deployments"],
  ["evidence", "Evidence"],
  ["rca", "RCA"],
  ["hypotheses", "Hypotheses"],
  ["verification", "Verification"],
] as const;

export function IncidentDetailPage() {
  const { incidentId: incidentIdParam } = useParams();
  const incidentId = Number(incidentIdParam);
  const validIncidentId = Number.isInteger(incidentId) && incidentId > 0;

  const incident = useAsync(
    (signal) => getIncident(incidentId, signal),
    [incidentId],
    { enabled: validIncidentId },
  );
  const timeline = useAsync(
    (signal) => getIncidentTimeline(incidentId, signal),
    [incidentId],
    { enabled: validIncidentId, keepPreviousData: true },
  );
  const evidence = useAsync(
    (signal) => getIncidentEvidence(incidentId, signal),
    [incidentId],
    {
      // Timeline construction also assembles evidence internally. Waiting for
      // that request avoids concurrent evidence builds against the same row.
      enabled: validIncidentId && timeline.status !== "loading",
      keepPreviousData: true,
    },
  );
  const latestInvestigation = useAsync(
    (signal) => getLatestIncidentInvestigation(incidentId, signal),
    [incidentId],
    { enabled: validIncidentId },
  );
  const rca = useAsync(
    (signal) => getLatestIncidentRCA(incidentId, signal),
    [incidentId],
    { enabled: validIncidentId, keepPreviousData: true },
  );

  const [liveInvestigation, setLiveInvestigation] =
    useState<Investigation | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    setLiveInvestigation(null);
    setStartError(null);
  }, [incidentId]);

  useEffect(() => {
    if (latestInvestigation.status === "success") {
      setLiveInvestigation(latestInvestigation.data);
    }
  }, [latestInvestigation.status, latestInvestigation.data]);

  useEffect(() => {
    if (
      !liveInvestigation ||
      !["queued", "running"].includes(liveInvestigation.status)
    ) {
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      try {
        const next = await getInvestigation(liveInvestigation.id);
        if (cancelled) {
          return;
        }
        setLiveInvestigation(next);
        if (next.status === "completed") {
          incident.reload();
          timeline.reload();
          evidence.reload();
          rca.reload();
        }
      } catch {
        // Keep the last known job state and try again on the next render cycle.
        if (!cancelled) {
          setLiveInvestigation((current) =>
            current ? { ...current, updated_at: current.updated_at } : current,
          );
        }
      }
    }, 2500);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [liveInvestigation, incident, timeline, evidence, rca]);

  async function handleStartInvestigation() {
    setIsStarting(true);
    setStartError(null);
    try {
      const started = await startInvestigation(incidentId);
      setLiveInvestigation(started);
    } catch (error) {
      setStartError(getErrorMessage(error, "Could not start investigation"));
    } finally {
      setIsStarting(false);
    }
  }

  if (!validIncidentId) {
    return (
      <section className="page page--narrow">
        <ErrorState
          title="Invalid incident"
          message="The incident ID in this URL is not valid."
        />
        <Link className="button" to={paths.incidents}>
          Back to incidents
        </Link>
      </section>
    );
  }

  if (incident.status === "loading") {
    return <LoadingState label="Loading incident…" />;
  }

  if (incident.status === "error") {
    return (
      <section className="page page--narrow">
        <ErrorState
          title="Incident unavailable"
          message={incident.error}
          onRetry={incident.reload}
        />
        <Link className="button button--ghost" to={paths.incidents}>
          Back to incidents
        </Link>
      </section>
    );
  }

  if (incident.status !== "success") {
    return null;
  }

  const item = incident.data;
  const timelineData = timeline.data;
  const errors =
    timelineData?.entries.filter((entry) =>
      ["error", "log"].includes(entry.category),
    ) ?? [];
  const metrics =
    timelineData?.entries.filter((entry) => entry.category === "metric") ?? [];
  const deployments =
    timelineData?.entries.filter((entry) => entry.category === "deployment") ??
    [];
  const investigationRunning =
    liveInvestigation?.status === "queued" ||
    liveInvestigation?.status === "running";

  return (
    <article className="page investigation-page">
      <header className="investigation-hero">
        <div className="investigation-hero__crumb">
          <Link to={paths.incidents}>Incidents</Link>
          <span>/</span>
          <span className="mono">#{item.id}</span>
        </div>
        <div className="investigation-hero__main">
          <div>
            <div className="investigation-hero__badges">
              <SeverityBadge severity={item.severity} />
              <StatusBadge status={item.status} />
              <span className="environment-badge mono">{item.environment}</span>
            </div>
            <h1>{item.title}</h1>
            <p className="lede">
              Started {formatRelativeTime(item.started_at)} ·{" "}
              {formatNumber(item.occurrence_count)} occurrence
              {item.occurrence_count === 1 ? "" : "s"}
            </p>
          </div>
          <div className="investigation-hero__actions">
            <button
              type="button"
              className="button"
              onClick={handleStartInvestigation}
              disabled={isStarting || investigationRunning}
            >
              {isStarting
                ? "Starting…"
                : investigationRunning
                  ? "Investigation running"
                  : liveInvestigation
                    ? "Run again"
                    : "Start investigation"}
            </button>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => {
                incident.reload();
                timeline.reload();
                evidence.reload();
                latestInvestigation.reload();
                rca.reload();
              }}
            >
              Refresh
            </button>
          </div>
        </div>
        {startError ? (
          <p className="inline-error investigation-hero__error" role="alert">
            {startError}
          </p>
        ) : null}
        {liveInvestigation ? (
          <InvestigationProgress investigation={liveInvestigation} />
        ) : latestInvestigation.status === "loading" ? (
          <p className="investigation-hero__checking">Checking job status…</p>
        ) : null}
      </header>

      <nav className="section-nav" aria-label="Investigation sections">
        {SECTION_LINKS.map(([id, label]) => (
          <a key={id} href={`#${id}`}>
            {label}
          </a>
        ))}
      </nav>

      <div className="investigation-layout">
        <main className="investigation-content">
          <SummarySection
            incident={item}
            entries={timelineData?.entries ?? []}
            markers={timelineData?.markers ?? null}
          />

          {timelineData ? (
            <>
              <TimelineSection timeline={timelineData} />
              <ErrorsSection entries={errors} />
              <MetricsSection entries={metrics} />
              <DeploymentsSection
                entries={deployments}
                correlation={timelineData.deployment_correlation}
              />
            </>
          ) : (
            <>
              <UnavailableSection
                id="timeline"
                title="Timeline"
                state={timeline.status}
                error={timeline.status === "error" ? timeline.error : null}
                onRetry={timeline.reload}
              />
              <UnavailableSection
                id="errors"
                title="Errors"
                state={timeline.status}
                error={timeline.status === "error" ? timeline.error : null}
                onRetry={timeline.reload}
              />
              <UnavailableSection
                id="metrics"
                title="Metrics"
                state={timeline.status}
                error={timeline.status === "error" ? timeline.error : null}
                onRetry={timeline.reload}
              />
              <UnavailableSection
                id="deployments"
                title="Deployments"
                state={timeline.status}
                error={timeline.status === "error" ? timeline.error : null}
                onRetry={timeline.reload}
              />
            </>
          )}

          {evidence.data ? (
            <EvidenceSection evidence={evidence.data} />
          ) : (
            <UnavailableSection
              id="evidence"
              title="Evidence"
              state={evidence.status}
              error={evidence.status === "error" ? evidence.error : null}
              onRetry={evidence.reload}
            />
          )}

          {rca.data ? (
            <>
              <RCASection record={rca.data} />
              <HypothesesSection record={rca.data} />
              <VerificationSection record={rca.data} />
            </>
          ) : (
            <>
              <PendingRCASection
                id="rca"
                title="RCA"
                loading={rca.status === "loading"}
                error={rca.status === "error" ? rca.error : null}
                running={investigationRunning}
                onRetry={rca.reload}
              />
              <PendingRCASection
                id="hypotheses"
                title="Hypotheses"
                loading={rca.status === "loading"}
                error={rca.status === "error" ? rca.error : null}
                running={investigationRunning}
                onRetry={rca.reload}
              />
              <PendingRCASection
                id="verification"
                title="Verification"
                loading={rca.status === "loading"}
                error={rca.status === "error" ? rca.error : null}
                running={investigationRunning}
                onRetry={rca.reload}
              />
            </>
          )}
        </main>
      </div>
    </article>
  );
}

function SummarySection({
  incident,
  entries,
  markers,
}: {
  incident: Awaited<ReturnType<typeof getIncident>>;
  entries: TimelineEntry[];
  markers:
    | Awaited<ReturnType<typeof getIncidentTimeline>>["markers"]
    | null;
}) {
  const markerRows = markers
    ? [
        ["First anomaly", markers.first_anomaly],
        ["First error", markers.first_relevant_error],
        ["First alert", markers.first_alert],
        ["Recent deployment", markers.recent_deployment],
        ["Recovery", markers.recovery],
      ]
    : [];

  return (
    <InvestigationSection
      id="summary"
      title="Summary"
      description="Incident scope, timing, and key investigation markers."
    >
      <dl className="summary-grid">
        <div>
          <dt>Incident ID</dt>
          <dd className="mono">#{incident.id}</dd>
        </div>
        <div>
          <dt>Project</dt>
          <dd className="mono">#{incident.project_id}</dd>
        </div>
        <div>
          <dt>Service</dt>
          <dd className="mono">
            {incident.service_id ? `#${incident.service_id}` : "Unscoped"}
          </dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>
            <time dateTime={incident.started_at}>
              {formatDateTime(incident.started_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt>Ended</dt>
          <dd>
            {incident.ended_at ? (
              <time dateTime={incident.ended_at}>
                {formatDateTime(incident.ended_at)}
              </time>
            ) : (
              "Ongoing"
            )}
          </dd>
        </div>
        <div>
          <dt>Signals</dt>
          <dd className="mono">{formatNumber(entries.length)}</dd>
        </div>
      </dl>

      {markerRows.length > 0 ? (
        <div className="marker-grid">
          {markerRows.map(([label, marker]) => (
            <div key={label as string} className="marker-card">
              <span>{label as string}</span>
              {marker && typeof marker !== "string" ? (
                <>
                  <strong>{marker.title}</strong>
                  <time
                    dateTime={marker.timestamp}
                    title={formatDateTime(marker.timestamp)}
                  >
                    {formatRelativeTime(marker.timestamp)}
                  </time>
                </>
              ) : (
                <strong className="muted">Not identified</strong>
              )}
            </div>
          ))}
        </div>
      ) : null}
    </InvestigationSection>
  );
}

function UnavailableSection({
  id,
  title,
  state,
  error,
  onRetry,
}: {
  id: string;
  title: string;
  state: string;
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <InvestigationSection id={id} title={title}>
      {state === "loading" ? (
        <LoadingState label={`Loading ${title.toLowerCase()}…`} />
      ) : (
        <SectionEmpty>
          {error ?? `${title} data is not available from the backend.`}{" "}
          <button type="button" className="text-button" onClick={onRetry}>
            Retry
          </button>
        </SectionEmpty>
      )}
    </InvestigationSection>
  );
}

function PendingRCASection({
  id,
  title,
  loading,
  error,
  running,
  onRetry,
}: {
  id: string;
  title: string;
  loading: boolean;
  error: string | null;
  running: boolean;
  onRetry: () => void;
}) {
  return (
    <InvestigationSection id={id} title={title}>
      {loading ? (
        <LoadingState label={`Loading ${title}…`} />
      ) : (
        <SectionEmpty pending={running}>
          {error ? (
            <>
              {error}{" "}
              <button type="button" className="text-button" onClick={onRetry}>
                Retry
              </button>
            </>
          ) : running ? (
            `${title} will appear when the investigation reaches the RCA stages.`
          ) : (
            `No persisted ${title} result is available. Start an investigation to generate it.`
          )}
        </SectionEmpty>
      )}
    </InvestigationSection>
  );
}
