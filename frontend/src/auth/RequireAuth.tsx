import { Center, Loader } from "@mantine/core";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import type { Role } from "../api/types";
import { NotFoundPage } from "../pages/NotFoundPage";
import { useAuth } from "./AuthProvider";

/** Only signed-in users (optionally of some roles) see `children`; others go to sign-in. */
export function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { status, user, endReason } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageLoader />;
  if (status === "signed-out" || !user) {
    // Come back here after signing in, unless someone signed out on purpose: the next person to sign in
    // starts on their own home page, not on the previous user's (maybe forbidden) page.
    return <Navigate to="/login" replace state={endReason === "signed-out" ? undefined : { from: location }} />;
  }
  // A page for another role doesn't exist for this user: the same answer as the API's 404.
  if (roles && !roles.includes(user.role)) return <NotFoundPage />;
  return children;
}

export function FullPageLoader() {
  return (
    <Center mih="100vh">
      <Loader aria-label="Loading" />
    </Center>
  );
}
