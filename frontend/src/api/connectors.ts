import { apiRequest } from "@/api/client";
import type {
  ConfiguredConnector,
  ConnectorConnectionTest,
  ConnectorListResponse,
  ConnectorType,
  ConnectorTypesResponse,
} from "@/api/types";

export type CreateConnectorPayload = {
  projectId: number;
  name: string;
  connectorType: ConnectorType;
  settings: Record<string, unknown>;
  credentials?: Record<string, string>;
  enabled?: boolean;
};

export type UpdateConnectorPayload = {
  name?: string;
  settings?: Record<string, unknown>;
  credentials?: Record<string, string | null>;
  enabled?: boolean;
};

export function listConnectorTypes(
  signal?: AbortSignal,
): Promise<ConnectorTypesResponse> {
  return apiRequest<ConnectorTypesResponse>("/api/v1/connectors/types", {
    signal,
  });
}

export function listConnectors(
  projectId: number,
  signal?: AbortSignal,
): Promise<ConnectorListResponse> {
  return apiRequest<ConnectorListResponse>("/api/v1/connectors", {
    query: { project_id: projectId },
    signal,
  });
}

export function createConnector(
  payload: CreateConnectorPayload,
  signal?: AbortSignal,
): Promise<ConfiguredConnector> {
  return apiRequest<ConfiguredConnector>("/api/v1/connectors", {
    method: "POST",
    body: {
      project_id: payload.projectId,
      name: payload.name,
      connector_type: payload.connectorType,
      settings: payload.settings,
      credentials: payload.credentials ?? {},
      enabled: payload.enabled ?? true,
    },
    signal,
  });
}

export function updateConnector(
  connectorId: number,
  payload: UpdateConnectorPayload,
  signal?: AbortSignal,
): Promise<ConfiguredConnector> {
  return apiRequest<ConfiguredConnector>(`/api/v1/connectors/${connectorId}`, {
    method: "PATCH",
    body: payload,
    signal,
  });
}

export function deleteConnector(
  connectorId: number,
  signal?: AbortSignal,
): Promise<void> {
  return apiRequest<void>(`/api/v1/connectors/${connectorId}`, {
    method: "DELETE",
    signal,
  });
}

export function enableConnector(
  connectorId: number,
  signal?: AbortSignal,
): Promise<ConfiguredConnector> {
  return apiRequest<ConfiguredConnector>(
    `/api/v1/connectors/${connectorId}/enable`,
    { method: "POST", signal },
  );
}

export function disableConnector(
  connectorId: number,
  signal?: AbortSignal,
): Promise<ConfiguredConnector> {
  return apiRequest<ConfiguredConnector>(
    `/api/v1/connectors/${connectorId}/disable`,
    { method: "POST", signal },
  );
}

export function testConnector(
  connectorId: number,
  signal?: AbortSignal,
): Promise<ConnectorConnectionTest> {
  return apiRequest<ConnectorConnectionTest>(
    `/api/v1/connectors/${connectorId}/test`,
    { method: "POST", signal },
  );
}
