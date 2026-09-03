import type {
  DeploymentCorrelation,
  TimelineEntry,
} from "@/api/types";
import {
  InvestigationSection,
  SectionEmpty,
} from "@/components/investigation/InvestigationSection";
import { formatDateTime, formatNumber, formatRelativeTime } from "@/utils/format";

export function ErrorsSection({ entries }: { entries: TimelineEntry[] }) {
  return (
    <InvestigationSection
      id="errors"
      title="Errors"
      description="Log failures and grouped errors found in the incident window."
      count={entries.length}
    >
      <SignalList entries={entries} empty="No error signals were found." />
    </InvestigationSection>
  );
}

export function MetricsSection({ entries }: { entries: TimelineEntry[] }) {
  return (
    <InvestigationSection
      id="metrics"
      title="Metrics"
      description="Metric observations and anomalies correlated with this incident."
      count={entries.length}
    >
      <SignalList entries={entries} empty="No metric signals were found." metric />
    </InvestigationSection>
  );
}

export function DeploymentsSection({
  entries,
  correlation,
}: {
  entries: TimelineEntry[];
  correlation: DeploymentCorrelation | null;
}) {
  return (
    <InvestigationSection
      id="deployments"
      title="Deployments"
      description="Deployments in the timeline window and their assessed relationship."
      count={entries.length}
      aside={
        correlation ? (
          <span
            className={`relation-pill ${
              correlation.is_related ? "relation-pill--related" : ""
            }`}
          >
            {correlation.is_related ? "Likely related" : "Not strongly related"} ·{" "}
            {formatPercent(correlation.relationship_score)}
          </span>
        ) : null
      }
    >
      <SignalList entries={entries} empty="No deployments were found." />
      {correlation ? (
        <div className="correlation-summary">
          <p>{correlation.summary}</p>
          {correlation.supporting_evidence.length > 0 ? (
            <ul className="compact-list">
              {correlation.supporting_evidence.map((item, index) => (
                <li key={`${item.kind}-${index}`}>{item.detail}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </InvestigationSection>
  );
}

function SignalList({
  entries,
  empty,
  metric = false,
}: {
  entries: TimelineEntry[];
  empty: string;
  metric?: boolean;
}) {
  if (entries.length === 0) {
    return <SectionEmpty>{empty}</SectionEmpty>;
  }

  return (
    <ul className="signal-list">
      {entries.map((entry) => {
        const occurrenceCount = readNumber(entry.metadata, "occurrence_count");
        const metricName =
          readNestedString(entry.metadata, "normalized_data", "metric_name") ??
          readString(entry.metadata, "metric_name");
        const metricValue =
          readNestedPrimitive(entry.metadata, "normalized_data", "value") ??
          readPrimitive(entry.metadata, "value");

        return (
          <li key={entry.id} className="signal-row">
            <div className={`signal-icon signal-icon--${entry.category}`}>
              {entry.category.slice(0, 1).toUpperCase()}
            </div>
            <div className="signal-row__body">
              <strong>{entry.title}</strong>
              {entry.summary && entry.summary !== entry.title ? (
                <p>{entry.summary}</p>
              ) : null}
              {metric && (metricName || metricValue !== null) ? (
                <div className="signal-meta mono">
                  {metricName ?? "value"}: {String(metricValue ?? "—")}
                </div>
              ) : null}
            </div>
            <div className="signal-row__aside">
              {occurrenceCount !== null ? (
                <span className="occurrence-pill">
                  {formatNumber(occurrenceCount)} occurrences
                </span>
              ) : null}
              <time
                dateTime={entry.timestamp}
                title={formatDateTime(entry.timestamp)}
              >
                {formatRelativeTime(entry.timestamp)}
              </time>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function readPrimitive(
  object: Record<string, unknown>,
  key: string,
): string | number | boolean | null {
  const value = object[key];
  return typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
    ? value
    : null;
}

function readString(
  object: Record<string, unknown>,
  key: string,
): string | null {
  const value = object[key];
  return typeof value === "string" ? value : null;
}

function readNumber(
  object: Record<string, unknown>,
  key: string,
): number | null {
  const value = object[key];
  return typeof value === "number" ? value : null;
}

function readNestedPrimitive(
  object: Record<string, unknown>,
  parent: string,
  key: string,
): string | number | boolean | null {
  const nested = object[parent];
  return nested && typeof nested === "object"
    ? readPrimitive(nested as Record<string, unknown>, key)
    : null;
}

function readNestedString(
  object: Record<string, unknown>,
  parent: string,
  key: string,
): string | null {
  const nested = object[parent];
  return nested && typeof nested === "object"
    ? readString(nested as Record<string, unknown>, key)
    : null;
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
