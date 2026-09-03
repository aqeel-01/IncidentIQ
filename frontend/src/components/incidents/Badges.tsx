import type { IncidentSeverity, IncidentStatus } from "@/api/types";
import {
  SEVERITY_LABELS,
  STATUS_LABELS,
  isActiveStatus,
} from "@/features/incidents/constants";

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return (
    <span
      className={`badge badge--severity badge--${severity.toLowerCase()}`}
      title={`Severity: ${SEVERITY_LABELS[severity]}`}
    >
      {SEVERITY_LABELS[severity]}
    </span>
  );
}

export function StatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <span
      className={`badge badge--status badge--${status.toLowerCase()}`}
      title={`Status: ${STATUS_LABELS[status]}`}
    >
      {isActiveStatus(status) ? (
        <span className="badge__dot" aria-hidden="true" />
      ) : null}
      {STATUS_LABELS[status]}
    </span>
  );
}
