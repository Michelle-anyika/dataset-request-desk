import { Navigate, Route, Routes } from "react-router";

import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { AssignEpisodesPage } from "./episodes/AssignEpisodesPage";
import { AppLayout } from "./layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RequestsPage } from "./pages/RequestsPage";
import { NewRequestPage } from "./requests/NewRequestPage";
import { RequestDetailPage } from "./requests/RequestDetailPage";
import { UsersPage } from "./pages/UsersPage";

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
