/**
 * Route guards.
 *
 * These improve the experience — they do not secure anything. Every protected
 * resource is authorised server-side on each request; a user who forces their
 * way to a route simply gets an empty screen and a 403 from the API.
 */

import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { LoadingState } from "@/design-system/components/primitives";
import { ROLE_HOME, useAuth } from "@/lib/auth";
import type { RoleName } from "@/lib/types";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <LoadingState label="Checking your session" />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/**
 * Confines each role to its own workspace. A user who lands on another
 * portal's route is redirected to their own home rather than shown a
 * half-populated screen.
 */
export function RequireRole({ role, children }: { role: RoleName; children: ReactNode }) {
  const { status, hasRole, primaryRole } = useAuth();

  if (status === "loading") return <LoadingState label="Checking your session" />;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  if (!hasRole(role)) {
    return <Navigate to={primaryRole ? ROLE_HOME[primaryRole] : "/login"} replace />;
  }
  return <>{children}</>;
}

/** Sends an authenticated user to the workspace matching their role. */
export function RoleLanding() {
  const { status, primaryRole } = useAuth();

  if (status === "loading") return <LoadingState label="Loading your workspace" />;
  if (status === "anonymous" || !primaryRole) return <Navigate to="/login" replace />;
  return <Navigate to={ROLE_HOME[primaryRole]} replace />;
}
