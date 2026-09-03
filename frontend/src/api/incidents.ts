import { apiRequest } from "@/api/client";
import type {
  Incident,
  IncidentListResponse,
  IncidentSeverity,
  IncidentStatus,
  IncidentSummary,
} from "@/api/types";

export type ListIncidentsParams = {
  projectId: number;
  page?: number;
  pageSize?: number;
  severity?: IncidentSeverity[];
  status?: IncidentStatus[];
};

export function listIncidents(
  params: ListIncidentsParams,
  signal?: AbortSignal,
): Promise<IncidentListResponse> {
  // FastAPI accepts repeated query keys for list filters; encode manually.
  const search = new URLSearchParams({
    project_id: String(params.projectId),
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  });
  for (const severity of params.severity ?? []) {
    search.append("severity", severity);
  }
  for (const status of params.status ?? []) {
    search.append("status", status);
  }

  return apiRequest<IncidentListResponse>(
    `/api/v1/incidents?${search.toString()}`,
    { signal },
  );
}

export type IncidentSummaryParams = {
  projectId: number;
  recentHours?: number;
};

export function getIncidentSummary(
  params: IncidentSummaryParams,
  signal?: AbortSignal,
): Promise<IncidentSummary> {
  return apiRequest<IncidentSummary>("/api/v1/incidents/summary", {
    query: {
      project_id: params.projectId,
      recent_hours: params.recentHours,
    },
    signal,
  });
}

export function getIncident(
  incidentId: number,
  signal?: AbortSignal,
): Promise<Incident> {
  return apiRequest<Incident>(`/api/v1/incidents/${incidentId}`, { signal });
}
