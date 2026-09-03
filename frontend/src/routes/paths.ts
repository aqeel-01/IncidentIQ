export const paths = {
  home: "/",
  login: "/login",
  system: "/system",
  incidents: "/incidents",
  incidentDetail: (incidentId: string | number) => `/incidents/${incidentId}`,
} as const;
