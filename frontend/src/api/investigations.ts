import { apiRequest } from "@/api/client";
import { isApiError } from "@/api/errors";
import type { Investigation } from "@/api/types";

export function startInvestigation(
  incidentId: number,
  signal?: AbortSignal,
): Promise<Investigation> {
  return apiRequest<Investigation>(
    `/api/v1/incidents/${incidentId}/investigate`,
    { method: "POST", signal },
  );
}

export function getInvestigation(
  investigationId: string,
  signal?: AbortSignal,
): Promise<Investigation> {
  return apiRequest<Investigation>(
    `/api/v1/investigations/${investigationId}`,
    { signal },
  );
}

export async function getLatestIncidentInvestigation(
  incidentId: number,
  signal?: AbortSignal,
): Promise<Investigation | null> {
  try {
    return await apiRequest<Investigation>(
      `/api/v1/investigations/by-incident/${incidentId}/latest`,
      { signal },
    );
  } catch (error) {
    if (isApiError(error) && error.isNotFound) {
      return null;
    }
    throw error;
  }
}
