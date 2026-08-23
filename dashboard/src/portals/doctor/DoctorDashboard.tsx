/**
 * Doctor dashboard.
 *
 * Not an analytics page. It triages: urgent cases first, then high, then the
 * rest — each row a direct route into the review workstation.
 */

import { Link } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Metric,
  Panel,
} from "@/design-system/components/primitives";
import { CATEGORY_LABELS, RISK_META, RiskBadge } from "@/design-system/risk/RiskDisplay";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useQuery } from "@/lib/useApi";
import type { FollowUp, Page, RiskQueueItem } from "@/lib/types";

export function DoctorDashboard() {
  const { user } = useAuth();

  const queue = useQuery(
    (signal) =>
      api.get<Page<RiskQueueItem>>(
        "/reviews/queue",
        { status: "pending", page_size: 100 },
        signal,
      ),
    [],
  );
  const followUps = useQuery(
    (signal) =>
      api.get<Page<FollowUp>>(
        "/followups",
        { status: "scheduled", due_before: new Date().toISOString().slice(0, 10) },
        signal,
      ),
    [],
  );

  if (queue.loading) return <LoadingState label="Loading your queue" />;
  if (queue.error) {
    return (
      <ErrorState
        message={queue.error.message}
        offline={queue.error.isOffline}
        onRetry={queue.refetch}
      />
    );
  }

  const items = queue.data?.items ?? [];
  const byLevel = (level: string) => items.filter((i) => i.risk?.risk_level === level);
  const urgent = byLevel("urgent");
  const high = byLevel("high");
  const rest = items.filter(
    (i) => !["urgent", "high"].includes(i.risk?.risk_level ?? ""),
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={`Good ${dayPart()}, Dr ${lastName(user?.full_name)}`}
        subtitle="Cases awaiting your clinical review."
        actions={
          <Link to="/doctor/risk-queue">
            <Button variant="secondary">Open full queue</Button>
          </Link>
        }
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Urgent review"
          value={urgent.length}
          tone={urgent.length ? "danger" : "neutral"}
        />
        <Metric label="High priority" value={high.length} tone={high.length ? "warn" : "neutral"} />
        <Metric label="Pending total" value={items.length} />
        <Metric
          label="Follow-ups due"
          value={followUps.data?.total ?? 0}
          tone={(followUps.data?.total ?? 0) > 0 ? "warn" : "neutral"}
        />
      </section>

      {items.length === 0 ? (
        <EmptyState
          title="Your queue is clear"
          description="No screenings are waiting for review right now."
        />
      ) : (
        <>
          {urgent.length > 0 && <QueueSection title="Needs urgent attention" items={urgent} />}
          {high.length > 0 && <QueueSection title="High priority" items={high} />}
          {rest.length > 0 && (
            <QueueSection title="Awaiting review" items={rest.slice(0, 8)} />
          )}
        </>
      )}
    </div>
  );
}

function QueueSection({ title, items }: { title: string; items: RiskQueueItem[] }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[var(--rs-text-lg)] font-semibold">{title}</h2>
      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <CaseRow key={item.review.id} item={item} />
        ))}
      </div>
    </section>
  );
}

export function CaseRow({ item }: { item: RiskQueueItem }) {
  const level = item.risk?.risk_level;

  return (
    <Panel
      className="flex flex-wrap items-center justify-between gap-4"
      style={
        level
          ? { borderLeft: `3px solid var(--rs-risk-${level})` }
          : undefined
      }
    >
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{item.patient.full_name}</span>
          <span className="rs-numeric text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
            {item.patient.patient_code}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[var(--rs-text-xs)]">
          {level && <RiskBadge level={level} size="sm" />}
          <span style={{ color: "var(--rs-ink-muted)" }}>
            {item.worst_result?.category
              ? CATEGORY_LABELS[item.worst_result.category]
              : "No AI result"}
          </span>
          {!item.quality_acceptable && (
            <span style={{ color: "var(--rs-warn)" }}>· Image quality limited</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {level && (
          <span
            className="hidden text-[var(--rs-text-xs)] sm:inline"
            style={{ color: "var(--rs-ink-subtle)" }}
          >
            {RISK_META[level].description}
          </span>
        )}
        <Link to={`/doctor/reviews/${item.review.id}`}>
          <Button variant="primary">Review case</Button>
        </Link>
      </div>
    </Panel>
  );
}

function dayPart(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
}

function lastName(fullName?: string): string {
  if (!fullName) return "";
  const parts = fullName.trim().split(/\s+/);
  return parts[parts.length - 1] ?? "";
}
