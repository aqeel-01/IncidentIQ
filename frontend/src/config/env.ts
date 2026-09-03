export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, ""),
  isDev: import.meta.env.DEV,
} as const;
