import type { IncidentSeverity, IncidentStatus } from "@/api/types";

export const SEVERITIES: readonly IncidentSeverity[] = [
  "CRITICAL",
  "HIGH",
  "MEDIUM",
  "LOW",
  "INFO",
];

export const STATUSES: readonly IncidentStatus[] = [
  "OPEN",
  "INVESTIGATING",
  "IDENTIFIED",
  "RESOLVED",
  "CLOSED",
];

export const ACTIVE_STATUSES: readonly IncidentStatus[] = [
  "OPEN",
  "INVESTIGATING",
  "IDENTIFIED",
];

export const SEVERITY_LABELS: Record<IncidentSeverity, string> = {
  CRITICAL: "Critical",
  HIGH: "High",
  MEDIUM: "Medium",
  LOW: "Low",
  INFO: "Info",
};

export const STATUS_LABELS: Record<IncidentStatus, string> = {
  OPEN: "Open",
  INVESTIGATING: "Investigating",
  IDENTIFIED: "Identified",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

export const PAGE_SIZES = [10, 20, 50] as const;
export const DEFAULT_PAGE_SIZE = 20;
export const RECENT_WINDOW_HOURS = 24;

export function isSeverity(value: string): value is IncidentSeverity {
  return (SEVERITIES as readonly string[]).includes(value);
}

export function isStatus(value: string): value is IncidentStatus {
  return (STATUSES as readonly string[]).includes(value);
}

export function isActiveStatus(status: IncidentStatus): boolean {
  return ACTIVE_STATUSES.includes(status);
}
