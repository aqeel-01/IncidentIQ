import { apiRequest } from "@/api/client";
import type { HealthResponse, ReadinessResponse } from "@/api/types";

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health", { auth: false, signal });
}

export function getReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>("/health/ready", { auth: false, signal });
}
