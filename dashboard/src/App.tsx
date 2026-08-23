/**
 * Application routing.
 *
 * Four separate role workspaces, each with its own route tree, navigation,
 * visual identity and information hierarchy — not one dashboard with items
 * conditionally hidden.
 */

import { Route, Routes } from "react-router-dom";

import { LoginPage } from "@/app/LoginPage";
import { RequireAuth, RequireRole, RoleLanding } from "@/app/RouteGuards";
import { AdminPortal } from "@/portals/admin/AdminPortal";
import { DoctorPortal } from "@/portals/doctor/DoctorPortal";
import { PatientPortal } from "@/portals/patient/PatientPortal";
import { WorkerPortal } from "@/portals/worker/WorkerPortal";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/admin/*"
        element={
          <RequireAuth>
            <RequireRole role="admin">
              <AdminPortal />
            </RequireRole>
          </RequireAuth>
        }
      />

      <Route
        path="/user/*"
        element={
          <RequireAuth>
            <RequireRole role="health_worker">
              <WorkerPortal />
            </RequireRole>
          </RequireAuth>
        }
      />

      <Route
        path="/doctor/*"
        element={
          <RequireAuth>
            <RequireRole role="doctor">
              <DoctorPortal />
            </RequireRole>
          </RequireAuth>
        }
      />

      <Route
        path="/patient/*"
        element={
          <RequireAuth>
            <RequireRole role="patient">
              <PatientPortal />
            </RequireRole>
          </RequireAuth>
        }
      />

      {/* Anything else routes the signed-in user to their own workspace. */}
      <Route path="*" element={<RoleLanding />} />
    </Routes>
  );
}
