import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "@/auth/AuthContext";
import { ErrorBoundary } from "@/components/feedback/ErrorBoundary";
import { AppRouter } from "@/routes/router";

export function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
