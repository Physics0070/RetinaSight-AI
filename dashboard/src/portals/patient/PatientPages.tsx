/**
 * Patient portal pages.
 *
 * Language rules applied throughout: no clinical abbreviations, no model
 * internals, no confidence percentages, and never the word "diagnosis".
 */

import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
} from "@/design-system/components/primitives";
import { CATEGORY_PATIENT_LABELS } from "@/design-system/risk/RiskDisplay";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useQuery } from "@/lib/useApi";
import type {
  Consent,
  FollowUp,
  Page,
  Patient,
  Referral,
  ScreeningSession,
  ScreeningSessionDetail,
} from "@/lib/types";
import { ProfileRow } from "@/portals/worker/WorkerPages";
import { formatFriendlyDate } from "./PatientHome";

/* -------------------------------------------------------------------------- */
export function PatientScreenings() {
  const screenings = useQuery(
    (signal) => api.get<Page<ScreeningSession>>("/screenings", { page_size: 50 }, signal),
    [],
  );

  if (screenings.loading) return <LoadingState label="Loading your results" />;
  if (screenings.error) {
    return <ErrorState message={screenings.error.message} onRetry={screenings.refetch} />;
  }

  const items = screenings.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Your screenings" subtitle="Every eye screening you have had." />

      {items.length === 0 && (
        <EmptyState
          title="No screenings yet"
          description="When you have an eye screening, it will appear here."
        />
      )}

      <div className="flex flex-col gap-3">
        {items.map((session) => (
          <Panel key={session.id} className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              <span className="font-semibold">
                {formatFriendlyDate(session.started_at ?? session.created_at)}
              </span>
              <span style={{ color: "var(--rs-ink-muted)" }}>
                {friendlyState(session.state)}
              </span>
            </div>
            <Link to={`/patient/screenings/${session.id}`}>
              <Button variant="secondary">See details</Button>
            </Link>
          </Panel>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function PatientScreeningDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();

  const session = useQuery(
    (signal) =>
      api.get<ScreeningSessionDetail>(`/screenings/${sessionId}`, undefined, signal),
    [sessionId],
  );

  if (session.loading) return <LoadingState label="Loading your screening" />;
  if (session.error) {
    return <ErrorState message={session.error.message} onRetry={session.refetch} />;
  }

  const detail = session.data;
  if (!detail) return null;

  const result = detail.results.find((r) => r.category);
  const reviewed = ["follow_up", "completed"].includes(detail.state);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Your screening"
        subtitle={formatFriendlyDate(detail.started_at ?? detail.created_at)}
        backTo="/patient/screenings"
        backLabel="All screenings"
      />

      <Panel className="flex flex-col gap-3">
        <span className="rs-label">What the screening found</span>
        {result?.category ? (
          <>
            <p className="text-[var(--rs-text-lg)] font-semibold">
              {CATEGORY_PATIENT_LABELS[result.category]}
            </p>
            <p style={{ color: "var(--rs-ink-muted)" }}>
              {reviewed
                ? "An eye doctor has looked at your photographs."
                : "An eye doctor is reviewing your photographs. This is not a final answer yet."}
            </p>
          </>
        ) : (
          <p style={{ color: "var(--rs-ink-muted)" }}>
            Your photographs are still being checked.
          </p>
        )}
      </Panel>

      {detail.risk && (
        <Panel className="flex flex-col gap-2">
          <span className="rs-label">What happens next</span>
          <p className="text-[var(--rs-text-lg)] font-semibold">
            {friendlyAction(detail.risk.recommended_action)}
          </p>
        </Panel>
      )}

      <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-subtle)" }}>
        A computer helps check your photographs, and an eye doctor reviews the
        result. If anything is unclear, ask your health worker.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function PatientReferrals() {
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { page_size: 50 }, signal),
    [],
  );

  if (referrals.loading) return <LoadingState label="Loading" />;
  if (referrals.error) {
    return <ErrorState message={referrals.error.message} onRetry={referrals.refetch} />;
  }

  const items = referrals.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Specialist referrals" />

      {items.length === 0 && (
        <EmptyState
          title="No referrals"
          description="You have not been referred to a specialist."
        />
      )}

      <div className="flex flex-col gap-3">
        {items.map((referral) => (
          <Panel key={referral.id} className="flex flex-col gap-2">
            <span className="font-semibold">
              {referral.priority === "urgent"
                ? "See an eye specialist as soon as possible"
                : referral.priority === "consultation"
                  ? "Please book an appointment with an eye specialist"
                  : "Routine monitoring recommended"}
            </span>
            <span style={{ color: "var(--rs-ink-muted)" }}>
              Requested on {formatFriendlyDate(referral.created_at)}
            </span>
          </Panel>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function PatientFollowUps() {
  const followUps = useQuery(
    (signal) => api.get<Page<FollowUp>>("/followups", { page_size: 50 }, signal),
    [],
  );

  if (followUps.loading) return <LoadingState label="Loading" />;
  if (followUps.error) {
    return <ErrorState message={followUps.error.message} onRetry={followUps.refetch} />;
  }

  const items = followUps.data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Your next visit" />

      {items.length === 0 && (
        <EmptyState title="No visit scheduled" description="Nothing is booked right now." />
      )}

      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <Panel key={item.id} className="flex flex-col gap-2">
            <span className="text-[var(--rs-text-lg)] font-semibold">
              {formatFriendlyDate(item.due_date)}
            </span>
            {item.instructions && <p>{item.instructions}</p>}
            <span style={{ color: "var(--rs-ink-muted)" }}>
              {item.status === "completed" ? "Completed" : "Scheduled"}
            </span>
          </Panel>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function PatientNotifications() {
  const followUps = useQuery(
    (signal) => api.get<Page<FollowUp>>("/followups", { page_size: 20 }, signal),
    [],
  );
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { page_size: 20 }, signal),
    [],
  );

  if (followUps.loading) return <LoadingState label="Loading updates" />;

  const updates = [
    ...(referrals.data?.items ?? []).map((r) => ({
      id: r.id,
      when: r.created_at,
      text:
        r.priority === "urgent"
          ? "You have been referred to an eye specialist. Please arrange this soon."
          : "You have been referred to an eye specialist.",
    })),
    ...(followUps.data?.items ?? []).map((f) => ({
      id: f.id,
      when: f.created_at,
      text: `A follow-up visit was scheduled for ${formatFriendlyDate(f.due_date)}.`,
    })),
  ].sort((a, b) => b.when.localeCompare(a.when));

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Updates" />

      {updates.length === 0 && <EmptyState title="Nothing new" />}

      <div className="flex flex-col gap-3">
        {updates.map((update) => (
          <Panel key={update.id} className="flex flex-col gap-1">
            <p>{update.text}</p>
            <span className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-subtle)" }}>
              {formatFriendlyDate(update.when)}
            </span>
          </Panel>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function PatientProfile() {
  const profile = useQuery((signal) => api.get<Patient>("/patients/me", undefined, signal), []);
  const consents = useQuery(
    (signal) => api.get<Consent[]>("/patients/me/consents", undefined, signal),
    [],
  );
  const { user, logout } = useAuth();

  if (profile.loading) return <LoadingState label="Loading your details" />;
  if (profile.error) {
    return <ErrorState message={profile.error.message} onRetry={profile.refetch} />;
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="My details" />

      <Panel className="flex flex-col gap-3">
        <ProfileRow label="Name" value={profile.data?.full_name ?? user?.full_name} />
        <ProfileRow label="Patient code" value={profile.data?.patient_code} />
        <ProfileRow label="Phone" value={profile.data?.phone} />
      </Panel>

      <Panel className="flex flex-col gap-3">
        <span className="rs-label">What you agreed to</span>
        {(consents.data ?? []).length === 0 && (
          <p style={{ color: "var(--rs-ink-muted)" }}>No consent records yet.</p>
        )}
        {(consents.data ?? []).map((consent) => (
          <div key={consent.id} className="flex items-center justify-between gap-3">
            <span>{friendlyConsent(consent.consent_type)}</span>
            <span style={{ color: consent.granted ? "var(--rs-ok)" : "var(--rs-ink-subtle)" }}>
              {consent.granted ? "Agreed" : "Not agreed"}
            </span>
          </div>
        ))}
      </Panel>

      <Button variant="ghost" onClick={() => void logout()}>
        Sign out
      </Button>
    </div>
  );
}

export function PatientSettings() {
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Settings" />
      <Panel>
        <p style={{ color: "var(--rs-ink-muted)" }}>
          To change your details or withdraw consent, please speak to your health
          worker at your clinic.
        </p>
      </Panel>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function friendlyState(state: string): string {
  const map: Record<string, string> = {
    completed: "Complete",
    doctor_review: "A doctor is reviewing this",
    referral_created: "You have been referred to a specialist",
    follow_up: "A follow-up visit was arranged",
    cancelled: "Cancelled",
    retake_required: "Photographs need to be taken again",
  };
  return map[state] ?? "In progress";
}

function friendlyAction(action: string): string {
  const map: Record<string, string> = {
    "Urgent ophthalmology referral": "See an eye specialist as soon as possible",
    "Specialist consultation": "Book an appointment with an eye specialist",
    "Prompt specialist consultation": "See an eye specialist soon",
    "Routine monitoring": "Keep having regular eye screenings",
    "Repeat the screening with a better capture":
      "Your photographs need to be taken again",
    "Clinician review required": "A doctor will look at your photographs",
  };
  return map[action] ?? action;
}

function friendlyConsent(type: string): string {
  const map: Record<string, string> = {
    screening: "Eye screening photographs",
    data_storage: "Storing your information securely",
    referral_sharing: "Sharing with a specialist if needed",
  };
  return map[type] ?? type.replace(/_/g, " ");
}
