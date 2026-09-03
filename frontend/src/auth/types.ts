export type AuthUser = {
  id: string;
  email: string;
  displayName: string;
};

export type AuthSession = {
  accessToken: string;
  user: AuthUser;
};

export type AuthStatus = "anonymous" | "authenticated" | "loading";
