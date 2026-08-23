/**
 * Health-worker portal — the field screening workspace.
 *
 * Optimised for speed and certainty in a PHC or outreach setting: task-first
 * dashboard, large tactile controls, and a capture flow that behaves like an
 * instrument rather than a form.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { PortalShell, type NavItem } from "@/app/PortalShell";
import { WorkerDashboard } from "./WorkerDashboard";
import { RegisterPatient } from "./RegisterPatient";
import { ScreeningWorkflow } from "./ScreeningWorkflow";
import {
  SyncQueuePage,
  WorkerFollowUps,
  WorkerPatients,
  WorkerProfile,
  WorkerReferrals,
  WorkerScreenings,
} from "./WorkerPages";

const NAV: NavItem[] = [
  { to: "/user/dashboard", label: "Today", glyph: "◉" },
  { to: "/user/patients", label: "Patients", glyph: "✚" },
  { to: "/user/screenings", label: "Screenings", glyph: "◎" },
  { to: "/user/referrals", label: "Referrals", glyph: "➜" },
  { to: "/user/follow-ups", label: "Follow-ups", glyph: "↻" },
  { to: "/user/sync", label: "Sync", glyph: "⇅" },
  { to: "/user/profile", label: "Profile", glyph: "◔" },
];

export function WorkerPortal() {
  return (
    <PortalShell role="health_worker" workspaceName="Field Screening" navItems={NAV}>
      <Routes>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<WorkerDashboard />} />
        <Route path="patients" element={<WorkerPatients />} />
        <Route path="patients/new" element={<RegisterPatient />} />
        <Route path="screening/:sessionId" element={<ScreeningWorkflow />} />
        <Route path="screenings" element={<WorkerScreenings />} />
        <Route path="referrals" element={<WorkerReferrals />} />
        <Route path="follow-ups" element={<WorkerFollowUps />} />
        <Route path="sync" element={<SyncQueuePage />} />
        <Route path="profile" element={<WorkerProfile />} />
        <Route path="*" element={<Navigate to="dashboard" replace />} />
      </Routes>
    </PortalShell>
  );
}
