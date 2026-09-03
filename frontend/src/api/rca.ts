import { apiRequest } from "@/api/client";
import { isApiError } from "@/api/errors";
import type { HistoricalRCARecord } from "@/api/types";

export async function getLatestIncidentRCA(
  incidentId: number,
  signal?: AbortSignal,
): Promise<HistoricalRCARecord | null> {
  try {
    return await apiRequest<HistoricalRCARecord>(
      `/api/v1/rca/incidents/${incidentId}/latest`,
      { signal },
    );
  } catch (error) {
    if (isApiError(error) && error.isNotFound) {
      return null;
    }
    throw error;
  }
}
