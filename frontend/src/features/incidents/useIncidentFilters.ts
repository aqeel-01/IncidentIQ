import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { IncidentSeverity, IncidentStatus } from "@/api/types";
import {
  ACTIVE_STATUSES,
  DEFAULT_PAGE_SIZE,
  PAGE_SIZES,
  isSeverity,
  isStatus,
} from "@/features/incidents/constants";

const PROJECT_STORAGE_KEY = "incidentiq.project_id";
const DEFAULT_PROJECT_ID = 1;

export type IncidentFilters = {
  projectId: number;
  page: number;
  pageSize: number;
  severity: IncidentSeverity[];
  status: IncidentStatus[];
};

export type FilterPreset = "all" | "active" | "critical";

function readStoredProjectId(): number {
  try {
    const raw = window.localStorage.getItem(PROJECT_STORAGE_KEY);
    const parsed = raw ? Number.parseInt(raw, 10) : NaN;
    return Number.isInteger(parsed) && parsed > 0 ? parsed : DEFAULT_PROJECT_ID;
  } catch {
    return DEFAULT_PROJECT_ID;
  }
}

function persistProjectId(projectId: number): void {
  try {
    window.localStorage.setItem(PROJECT_STORAGE_KEY, String(projectId));
  } catch {
    // Storage may be unavailable (private mode, quota); URL still holds state.
  }
}

function parsePositiveInt(value: string | null, fallback: number): number {
  const parsed = value ? Number.parseInt(value, 10) : NaN;
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseFilters(params: URLSearchParams): IncidentFilters {
  const pageSize = parsePositiveInt(params.get("page_size"), DEFAULT_PAGE_SIZE);
  return {
    projectId: parsePositiveInt(params.get("project"), readStoredProjectId()),
    page: parsePositiveInt(params.get("page"), 1),
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize)
      ? pageSize
      : DEFAULT_PAGE_SIZE,
    severity: params.getAll("severity").filter(isSeverity),
    status: params.getAll("status").filter(isStatus),
  };
}

function serializeFilters(filters: IncidentFilters): URLSearchParams {
  const params = new URLSearchParams();
  params.set("project", String(filters.projectId));
  if (filters.page > 1) {
    params.set("page", String(filters.page));
  }
  if (filters.pageSize !== DEFAULT_PAGE_SIZE) {
    params.set("page_size", String(filters.pageSize));
  }
  for (const severity of filters.severity) {
    params.append("severity", severity);
  }
  for (const status of filters.status) {
    params.append("status", status);
  }
  return params;
}

function sameSet<T>(a: readonly T[], b: readonly T[]): boolean {
  return a.length === b.length && a.every((value) => b.includes(value));
}

export function detectPreset(filters: IncidentFilters): FilterPreset | null {
  if (filters.severity.length === 0 && filters.status.length === 0) {
    return "all";
  }
  if (filters.severity.length === 0 && sameSet(filters.status, ACTIVE_STATUSES)) {
    return "active";
  }
  if (
    sameSet(filters.severity, ["CRITICAL"]) &&
    sameSet(filters.status, ACTIVE_STATUSES)
  ) {
    return "critical";
  }
  return null;
}

export function useIncidentFilters() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);

  const update = useCallback(
    (patch: Partial<IncidentFilters>, options: { resetPage?: boolean } = {}) => {
      setSearchParams(
        (current) => {
          const next = { ...parseFilters(current), ...patch };
          if (options.resetPage ?? true) {
            next.page = patch.page ?? 1;
          }
          persistProjectId(next.projectId);
          return serializeFilters(next);
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setPage = useCallback(
    (page: number) => update({ page }, { resetPage: false }),
    [update],
  );

  const toggleSeverity = useCallback(
    (severity: IncidentSeverity) =>
      update({
        severity: filters.severity.includes(severity)
          ? filters.severity.filter((value) => value !== severity)
          : [...filters.severity, severity],
      }),
    [filters.severity, update],
  );

  const toggleStatus = useCallback(
    (status: IncidentStatus) =>
      update({
        status: filters.status.includes(status)
          ? filters.status.filter((value) => value !== status)
          : [...filters.status, status],
      }),
    [filters.status, update],
  );

  const applyPreset = useCallback(
    (preset: FilterPreset) => {
      switch (preset) {
        case "all":
          update({ severity: [], status: [] });
          break;
        case "active":
          update({ severity: [], status: [...ACTIVE_STATUSES] });
          break;
        case "critical":
          update({ severity: ["CRITICAL"], status: [...ACTIVE_STATUSES] });
          break;
      }
    },
    [update],
  );

  return {
    filters,
    preset: detectPreset(filters),
    hasActiveFilters: filters.severity.length > 0 || filters.status.length > 0,
    setPage,
    setPageSize: (pageSize: number) => update({ pageSize }),
    setProjectId: (projectId: number) => update({ projectId }),
    setSeverity: (severity: IncidentSeverity[]) => update({ severity }),
    setStatus: (status: IncidentStatus[]) => update({ status }),
    toggleSeverity,
    toggleStatus,
    applyPreset,
    clearFilters: () => applyPreset("all"),
  };
}
