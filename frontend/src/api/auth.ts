import { apiRequest } from "@/api/client";
import type { AuthUser, ProjectRole } from "@/auth/types";

export type MembershipResponse = {
  project_id: number;
  project_name: string;
  project_slug: string;
  organization_id: number;
  role: ProjectRole;
};

export type AuthUserResponse = {
  id: number;
  email: string;
  full_name: string | null;
  organization_id: number;
  organization_name: string;
  organization_slug: string;
  is_active: boolean;
  memberships: MembershipResponse[];
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: AuthUserResponse;
};

export type BootstrapRequest = {
  organization_name: string;
  organization_slug: string;
  project_name: string;
  project_slug: string;
  email: string;
  password: string;
  full_name?: string;
};

export type BootstrapResponse = {
  organization_id: number;
  project_id: number;
  user: AuthUserResponse;
  access_token: string;
  token_type: string;
};

export function toAuthUser(payload: AuthUserResponse): AuthUser {
  return {
    id: String(payload.id),
    email: payload.email,
    displayName: payload.full_name?.trim() || payload.email.split("@")[0] || "User",
    organizationId: payload.organization_id,
    organizationName: payload.organization_name,
    memberships: payload.memberships.map((item) => ({
      projectId: item.project_id,
      projectName: item.project_name,
      projectSlug: item.project_slug,
      organizationId: item.organization_id,
      role: item.role,
    })),
  };
}

export function login(email: string, password: string, signal?: AbortSignal) {
  return apiRequest<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
    auth: false,
    signal,
  });
}

export function fetchCurrentUser(signal?: AbortSignal) {
  return apiRequest<AuthUserResponse>("/api/v1/auth/me", { signal });
}

export function bootstrap(body: BootstrapRequest, signal?: AbortSignal) {
  return apiRequest<BootstrapResponse>("/api/v1/auth/bootstrap", {
    method: "POST",
    body,
    auth: false,
    signal,
  });
}
