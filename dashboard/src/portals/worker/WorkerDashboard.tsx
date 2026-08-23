/**
 * Health-worker dashboard.
 *
 * Answers one question: what should I do next? Task counts come first, the
 * primary action dominates, and everything else is secondary.
 */

import { Link } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  ErrorState,
  LoadingState,
  Metric,
  Panel,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useQuery } from "@/lib/useApi";
import type { FollowUp, Page, Referral, ScreeningSession } from "@/lib/types";
import { ScreeningStateChip } from "./ScreeningStateChip";

const OPEN_STATES = new Set([
  "patient_selected",
  "capture_left_eye",
  "capture_right_eye",
  "quality_check",
  "retake_required",
  "ready_for_inference",
  "result_available",
  "explanation_available",
  "referral_pending",
]);

export function WorkerDashboard() {
  const { user } = useAuth();

  const screenings = useQuery(
    (signal) => api.get<Page<ScreeningSession>>("/screenings", { page_size: 100 }, signal),
    [],
  );
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { status: "created", page_size: 50 }, signal),
    [],
  );
  const followUps = useQuery(
    (signal) =>
      api.get<Page<FollowUp>>(
        "/followups",
        { status: "scheduled", due_before: today(), page_size: 50 },
        signal,
      ),
    [],
  );

  if (screenings.loading) return <LoadingState label="Loading your work" />;
  if (screenings.error) {
    return (
      <ErrorState
        message={screenings.error.message}
        offline={screenings.error.isOffline}
        onRetry={screenings.refetch}
      />
    );
  }

  const sessions = screenings.data?.items ?? [];
  const todayCount = sessions.filter((s) => isToday(s.created_at)).length;
  const open = sessions.filter((s) => OPEN_STATES.has(s.state));
  const pendingSync = sessions.filter((s) => s.sync_status === "pending");

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={greeting(user?.full_name)}
        subtitle="Your screening tasks for today."
      />

      {/* Primary action — visually dominant, thumb-reachable. */}
      <Panel className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <h2 className="text-[var(--rs-text-lg)] font-bold">Start a new screening</h2>
          <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
            Register the patient and capture both eyes.
          </p>
        </div>
        <Link to="/user/patients/new">
          <Button variant="primary" size="lg">
            New screening
          </Button>
        </Link>
      </Panel>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Screenings today" value={todayCount} />
        <Metric
          label="In progress"
          value={open.length}
          tone={open.length > 0 ? "warn" : "neutral"}
          hint={open.length ? "Resume below" : undefined}
        />
        <Metric
          label="Pending referrals"
          value={referrals.data?.total ?? 0}
          tone={(referrals.data?.total ?? 0) > 0 ? "warn" : "neutral"}
        />
        <Metric
          label="Follow-ups due"
          value={followUps.data?.total ?? 0}
          tone={(followUps.data?.total ?? 0) > 0 ? "warn" : "neutral"}
        />
      </section>

      {open.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-[var(--rs-text-lg)] font-semibold">Continue where you left off</h2>
          <div className="flex flex-col gap-2">
            {open.slice(0, 6).map((session) => (
              <Panel
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-3"
              >
                <div className="flex flex-col gap-1">
                  <ScreeningStateChip state={session.state} />
                  <span className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
                    Started {formatDateTime(session.started_at ?? session.created_at)}
                  </span>
                </div>
                <Link to={`/user/screening/${session.id}`}>
                  <Button variant="secondary">Resume</Button>
                </Link>
              </Panel>
            ))}
          </div>
        </section>
      )}

      {pendingSync.length > 0 && (
        <Panel className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold">
              {pendingSync.length} screening{pendingSync.length === 1 ? "" : "s"} waiting to sync
            </span>
            <span className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
              Captured offline and stored on this device.
            </span>
          </div>
          <Link to="/user/sync">
            <Button variant="secondary">View queue</Button>
          </Link>
        </Panel>
      )}
    </div>
  );
}

function greeting(name?: string): string {
  const hour = new Date().getHours();
  const period = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const first = name?.split(" ")[0];
  return first ? `${period}, ${first}` : period;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function isToday(iso: string): boolean {
  return iso.slice(0, 10) === today();
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
