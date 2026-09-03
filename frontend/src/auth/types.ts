export type ProjectRole = "ADMIN" | "ENGINEER" | "VIEWER";

export type ProjectMembership = {
  projectId: number;
  projectName: string;
  projectSlug: string;
  organizationId: number;
  role: ProjectRole;
};

export type AuthUser = {
  id: string;
  email: string;
  displayName: string;
  organizationId?: number;
  organizationName?: string;
  memberships: ProjectMembership[];
};

export type AuthSession = {
  accessToken: string;
  user: AuthUser;
};

export type AuthStatus = "anonymous" | "authenticated" | "loading";
