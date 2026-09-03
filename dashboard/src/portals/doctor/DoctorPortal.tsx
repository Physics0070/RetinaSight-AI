/**
 * Doctor portal — the clinical review workstation.
 *
 * Dark imaging ground, image-first layouts, and a queue that answers one
 * question: which patients need me now?
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { PortalShell, type NavItem } from "@/app/PortalShell";
import { DoctorDashboard } from "./DoctorDashboard";
import { RiskQueue } from "./RiskQueue";
import { CaseReview } from "./CaseReview";
import { PatientRecord } from "./PatientRecord";
import { Prescribe } from "./Prescribe";
import {
  DoctorAudit,
  DoctorFollowUps,
  DoctorPatients,
  DoctorProfile,
  DoctorReferrals,
  DoctorReviews,
} from "./DoctorPages";

const NAV: NavItem[] = [
  { to: "/doctor/dashboard", label: "Dashboard", glyph: "◉" },
  { to: "/doctor/risk-queue", label: "Risk queue", glyph: "▤" },
  { to: "/doctor/patients", label: "Patients", glyph: "✚" },
  { to: "/doctor/referrals", label: "Referrals", glyph: "➜" },
  { to: "/doctor/reviews", label: "Reviews", glyph: "⚕" },
  { to: "/doctor/follow-ups", label: "Follow-ups", glyph: "↻" },
  { to: "/doctor/audit", label: "My activity", glyph: "◷" },
  { to: "/doctor/profile", label: "Profile", glyph: "◔" },
];

export function DoctorPortal() {
  return (
    <PortalShell role="doctor" workspaceName="Clinical Review" navItems={NAV}>
      <Routes>
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<DoctorDashboard />} />
        <Route path="risk-queue" element={<RiskQueue />} />
        <Route path="reviews" element={<DoctorReviews />} />
        <Route path="reviews/:reviewId" element={<CaseReview />} />
        <Route path="patients" element={<DoctorPatients />} />
        <Route path="patients/:patientId" element={<PatientRecord />} />
        <Route path="patients/:patientId/prescribe" element={<Prescribe />} />
        <Route path="referrals" element={<DoctorReferrals />} />
        <Route path="follow-ups" element={<DoctorFollowUps />} />
        <Route path="audit" element={<DoctorAudit />} />
        <Route path="profile" element={<DoctorProfile />} />
        <Route path="*" element={<Navigate to="dashboard" replace />} />
      </Routes>
    </PortalShell>
  );
}
