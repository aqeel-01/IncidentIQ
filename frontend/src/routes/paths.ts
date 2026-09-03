export const paths = {
  home: "/",
  login: "/login",
  system: "/system",
  connectors: "/connectors",
  incidents: "/incidents",
  incidentDetail: (incidentId: string | number) => `/incidents/${incidentId}`,
} as const;
