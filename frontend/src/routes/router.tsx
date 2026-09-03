import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "@/auth/RequireAuth";
import { AppShell } from "@/components/layout/AppShell";
import { ConnectorsPage } from "@/pages/ConnectorsPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { IncidentsPage } from "@/pages/IncidentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SystemPage } from "@/pages/SystemPage";
import { paths } from "@/routes/paths";

export function AppRouter() {
  return (
    <Routes>
      <Route
        path={paths.login}
        element={
          <AppShell>
            <LoginPage />
          </AppShell>
        }
      />
      <Route
        path={paths.home}
        element={<Navigate to={paths.incidents} replace />}
      />
      <Route
        path={paths.incidents}
        element={
          <RequireAuth>
            <AppShell>
              <IncidentsPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path="/incidents/:incidentId"
        element={
          <RequireAuth>
            <AppShell>
              <IncidentDetailPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path={paths.connectors}
        element={
          <RequireAuth>
            <AppShell>
              <ConnectorsPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route
        path={paths.system}
        element={
          <RequireAuth>
            <AppShell>
              <SystemPage />
            </AppShell>
          </RequireAuth>
        }
      />
      <Route path="/home" element={<Navigate to={paths.home} replace />} />
      <Route
        path="*"
        element={
          <AppShell>
            <NotFoundPage />
          </AppShell>
        }
      />
    </Routes>
  );
}
