/**
 * Patient portal.
 *
 * Written for someone who may be anxious, may not read English fluently, and
 * is not a clinician. Rules for this portal:
 *
 *  - Plain language only; no clinical abbreviations, no model internals.
 *  - A screening result is never presented as a diagnosis.
 *  - The next step is always visible.
 *  - Large type, generous spacing, mobile-first with a bottom bar.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { PortalShell, type NavItem } from "@/app/PortalShell";
import { PatientHome } from "./PatientHome";
import {
  PatientFollowUps,
  PatientNotifications,
  PatientProfile,
  PatientReferrals,
  PatientScreeningDetail,
  PatientScreenings,
  PatientSettings,
} from "./PatientPages";

const NAV: NavItem[] = [
  { to: "/patient/home", label: "Home", glyph: "⌂" },
  { to: "/patient/screenings", label: "Results", glyph: "◎" },
  { to: "/patient/follow-ups", label: "Next visit", glyph: "↻" },
  { to: "/patient/notifications", label: "Updates", glyph: "◔" },
  { to: "/patient/profile", label: "Me", glyph: "☺" },
];

export function PatientPortal() {
  return (
    <PortalShell
      role="patient"
      workspaceName="My eye screening"
      navItems={NAV}
      layout="bottom-bar"
    >
      <Routes>
        <Route index element={<Navigate to="home" replace />} />
        <Route path="home" element={<PatientHome />} />
        <Route path="profile" element={<PatientProfile />} />
        <Route path="screenings" element={<PatientScreenings />} />
        <Route path="screenings/:sessionId" element={<PatientScreeningDetail />} />
        <Route path="referrals" element={<PatientReferrals />} />
        <Route path="follow-ups" element={<PatientFollowUps />} />
        <Route path="notifications" element={<PatientNotifications />} />
        <Route path="settings" element={<PatientSettings />} />
        <Route path="*" element={<Navigate to="home" replace />} />
      </Routes>
    </PortalShell>
  );
}
