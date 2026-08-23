/**
 * Admin portal — the command centre.
 *
 * Dense, monitoring-oriented, information-first. Every figure shown here is
 * read from the database; nothing is estimated or padded.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { PortalShell, type NavItem } from "@/app/PortalShell";
import { AdminDashboardPage } from "./AdminDashboard";
import { AdminUsers } from "./AdminUsers";
import { AdminModels } from "./AdminModels";
import { AdminConfiguration } from "./AdminConfiguration";
import {
  AdminAudit,
  AdminClinics,
  AdminPatients,
  AdminReferrals,
  AdminScreenings,
  AdminSystemHealth,
} from "./AdminPages";

const NAV: NavItem[] = [
  { to: "/admin/dashboard", label: "Overview", glyph: "◉" },
  { to: "/admin/users", label: "Users", glyph: "☰" },
  { to: "/admin/clinics", label: "Clinics", glyph: "⌂" },
  { to: "/admin/patients", label: "Patients", glyph: "✚" },
  { to: "/admin/screenings", label: "Screenings", glyph: "◎" },
  { to: "/admin/referrals", label: "Referrals", glyph: "➜" },
  { to: "/admin/models", label: "Models", glyph: "◈" },
  { to: "/admin/configuration", label: "Configuration", glyph: "⚙" },
  { to: "/admin/audit-logs", label: "Audit", glyph: "◷" },
  { to: "/admin/system-health", label: "System", glyph: "◍" },
];

export function AdminPortal() {
  return (
    <PortalShell role="admin" workspaceName="Administration" navItems={NAV}>
      <Routes>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<AdminDashboardPage />} />
        <Route path="users" element={<AdminUsers />} />
        <Route path="doctors" element={<AdminUsers roleFilter="doctor" />} />
        <Route path="health-workers" element={<AdminUsers roleFilter="health_worker" />} />
        <Route path="clinics" element={<AdminClinics />} />
        <Route path="patients" element={<AdminPatients />} />
        <Route path="screenings" element={<AdminScreenings />} />
        <Route path="referrals" element={<AdminReferrals />} />
        <Route path="models" element={<AdminModels />} />
        <Route path="configuration" element={<AdminConfiguration />} />
        <Route path="audit-logs" element={<AdminAudit />} />
        <Route path="system-health" element={<AdminSystemHealth />} />
        <Route path="settings" element={<AdminConfiguration />} />
        <Route path="*" element={<Navigate to="dashboard" replace />} />
      </Routes>
    </PortalShell>
  );
}
