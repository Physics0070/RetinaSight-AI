/**
 * Patient home.
 *
 * One question answered at the top: where am I in the process, and what happens
 * next? Everything else is secondary.
 */

import { Link } from "react-router-dom";

import {
  Button,
  ErrorState,
  LoadingState,
  Panel,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useQuery } from "@/lib/useApi";
import type { FollowUp, Page, Patient, Referral, ScreeningSession } from "@/lib/types";

/** Plain-language stage descriptions, keyed by workflow state. */
const STAGE_COPY: Record<string, { heading: string; body: string }> = {
  awaiting_screening: {
    heading: "You haven't had a screening yet",
    body: "A health worker will take photographs of the back of your eyes. It is quick and does not hurt.",
  },
  in_progress: {
    heading: "Your screening is in progress",
    body: "The health worker is capturing images of your eyes.",
  },
  awaiting_review: {
    heading: "A doctor is reviewing your screening",
    body: "Your images have been sent to an eye doctor. They will look at them and decide what happens next.",
  },
  reviewed: {
    heading: "A doctor has reviewed your screening",
    body: "You can see what they recommended below.",
  },
  completed: {
    heading: "Your screening is complete",
    body: "Keep an eye on your next visit date so your eyes stay monitored.",
  },
};

export function PatientHome() {
  const { user } = useAuth();

  const profile = useQuery(
    (signal) => api.get<Patient>("/patients/me", undefined, signal),
    [],
  );
  const screenings = useQuery(
    (signal) => api.get<Page<ScreeningSession>>("/screenings", { page_size: 20 }, signal),
    [],
  );
  const followUps = useQuery(
    (signal) => api.get<Page<FollowUp>>("/followups", { page_size: 10 }, signal),
    [],
  );
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { page_size: 10 }, signal),
    [],
  );

  if (profile.loading || screenings.loading) {
    return <LoadingState label="Loading your information" />;
  }
  if (profile.error) {
    return (
      <ErrorState
        message={profile.error.message}
        offline={profile.error.isOffline}
        onRetry={profile.refetch}
      />
    );
  }

  const sessions = screenings.data?.items ?? [];
  const latest = sessions[0] ?? null;
  const stage = resolveStage(latest);
  const copy = STAGE_COPY[stage];
  const nextFollowUp = (followUps.data?.items ?? [])
    .filter((f) => f.status === "scheduled")
    .sort((a, b) => a.due_date.localeCompare(b.due_date))[0];
  const openReferral = (referrals.data?.items ?? []).find(
    (r) => r.status !== "completed" && r.status !== "cancelled",
  );

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-[var(--rs-text-2xl)] font-bold">
          Hello{firstName(user?.full_name) ? `, ${firstName(user?.full_name)}` : ""}
        </h1>
        <p style={{ color: "var(--rs-ink-muted)" }}>Here's where things stand.</p>
      </header>

      {/* --- current stage --- */}
      <Panel className="flex flex-col gap-4">
        <StageTrack stage={stage} />
        <div className="flex flex-col gap-2">
          <h2 className="text-[var(--rs-text-xl)] font-bold">{copy.heading}</h2>
          <p style={{ color: "var(--rs-ink-muted)" }}>{copy.body}</p>
        </div>
      </Panel>

      {/* --- next step --- */}
      {nextFollowUp && (
        <Panel className="flex flex-col gap-2">
          <span className="rs-label">Your next visit</span>
          <p className="text-[var(--rs-text-lg)] font-semibold">
            {formatFriendlyDate(nextFollowUp.due_date)}
          </p>
          {nextFollowUp.instructions && <p>{nextFollowUp.instructions}</p>}
          <Link to="/patient/follow-ups">
            <Button variant="secondary">See visit details</Button>
          </Link>
        </Panel>
      )}

      {openReferral && (
        <Panel className="flex flex-col gap-2">
          <span className="rs-label">You've been referred to an eye specialist</span>
          <p style={{ color: "var(--rs-ink-muted)" }}>
            {openReferral.priority === "urgent"
              ? "Please arrange to see an eye specialist as soon as you can."
              : "Please arrange an appointment with an eye specialist."}
          </p>
          <Link to="/patient/referrals">
            <Button variant="secondary">See referral</Button>
          </Link>
        </Panel>
      )}

      {sessions.length > 0 && (
        <Panel className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold">Your screening results</span>
            <span style={{ color: "var(--rs-ink-muted)" }}>
              {sessions.length} screening{sessions.length === 1 ? "" : "s"} on record
            </span>
          </div>
          <Link to="/patient/screenings">
            <Button variant="secondary">View results</Button>
          </Link>
        </Panel>
      )}

      {/* This framing is required everywhere a result is mentioned. */}
      <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-subtle)" }}>
        Screening uses a computer to help check your eye photographs. It does not
        replace a doctor — an eye doctor reviews every screening.
      </p>
    </div>
  );
}

function resolveStage(session: ScreeningSession | null): string {
  if (!session) return "awaiting_screening";
  if (session.state === "completed") return "completed";
  if (["doctor_review", "referral_created", "referral_pending"].includes(session.state)) {
    return "awaiting_review";
  }
  if (["follow_up"].includes(session.state)) return "reviewed";
  return "in_progress";
}

/** Ordered progress track — position and label, not colour alone. */
function StageTrack({ stage }: { stage: string }) {
  const steps = [
    { key: "awaiting_screening", label: "Screening" },
    { key: "in_progress", label: "Photographs" },
    { key: "awaiting_review", label: "Doctor review" },
    { key: "reviewed", label: "Result" },
    { key: "completed", label: "Done" },
  ];
  const activeIndex = Math.max(
    0,
    steps.findIndex((s) => s.key === stage),
  );

  return (
    <ol className="flex items-start gap-1" aria-label="Your progress">
      {steps.map((step, index) => {
        const done = index < activeIndex;
        const active = index === activeIndex;
        return (
          <li key={step.key} className="flex flex-1 flex-col items-center gap-1.5">
            <div
              className="h-2 w-full rounded-full"
              style={{
                background:
                  done || active ? "var(--rs-accent)" : "var(--rs-surface-sunken)",
                opacity: done ? 0.5 : 1,
              }}
            />
            <span
              className="text-center text-[var(--rs-text-xs)]"
              style={{
                color: active ? "var(--rs-accent)" : "var(--rs-ink-subtle)",
                fontWeight: active ? 700 : 500,
              }}
            >
              {active && <span aria-hidden="true">● </span>}
              {step.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function firstName(fullName?: string): string {
  return fullName?.trim().split(/\s+/)[0] ?? "";
}

export function formatFriendlyDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
