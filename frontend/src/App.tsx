import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";

import { AuthProvider } from "./auth/AuthProvider";
import { FullPageLoader, RequireAuth } from "./auth/RequireAuth";
import { AssignEpisodesPage } from "./episodes/AssignEpisodesPage";
import { ImportReportPage } from "./imports/ImportReportPage";
import { ImportsPage } from "./imports/ImportsPage";
import { AppLayout } from "./layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RequestsPage } from "./pages/RequestsPage";
import { NewRequestPage } from "./requests/NewRequestPage";
import { RequestDetailPage } from "./requests/RequestDetailPage";
import { UsersPage } from "./pages/UsersPage";

// The charts library is large: load it only when someone opens analytics.
const AnalyticsPage = lazy(() => import("./analytics/AnalyticsPage").then((module) => ({ default: module.AnalyticsPage })));

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/requests" replace />} />
          <Route path="/requests" element={<RequestsPage />} />
          <Route
            path="/requests/new"
            element={
              <RequireAuth roles={["client"]}>
                <NewRequestPage />
              </RequireAuth>
            }
          />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          <Route
            path="/requests/:id/assign"
            element={
              <RequireAuth roles={["operator", "admin"]}>
                <AssignEpisodesPage />
              </RequireAuth>
            }
          />
          <Route
            path="/imports"
            element={
              <RequireAuth roles={["operator", "admin"]}>
                <ImportsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/imports/:id"
            element={
              <RequireAuth roles={["operator", "admin"]}>
                <ImportReportPage />
              </RequireAuth>
            }
          />
          <Route
            path="/analytics"
            element={
              <RequireAuth roles={["operator", "admin"]}>
                <Suspense fallback={<FullPageLoader />}>
                  <AnalyticsPage />
                </Suspense>
              </RequireAuth>
            }
          />
          <Route
            path="/users"
            element={
              <RequireAuth roles={["admin"]}>
                <UsersPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
