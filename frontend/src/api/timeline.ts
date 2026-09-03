import { apiRequest } from "@/api/client";
import type { TimelineResponse } from "@/api/types";

export function getIncidentTimeline(
  incidentId: number,
  signal?: AbortSignal,
): Promise<TimelineResponse> {
  return apiRequest<TimelineResponse>(`/api/v1/timeline/${incidentId}`, {
    signal,
  });
}
