import { apiRequest } from "@/api/client";
import type { EvidenceGroup } from "@/api/types";

export function getIncidentEvidence(
  incidentId: number,
  signal?: AbortSignal,
): Promise<EvidenceGroup> {
  return apiRequest<EvidenceGroup>(`/api/v1/evidence/${incidentId}`, {
    signal,
  });
}
