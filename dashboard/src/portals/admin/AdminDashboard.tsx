/**
 * Admin overview.
 *
 * Every number comes from `/admin/dashboard`, which counts rows in PostgreSQL.
 * An empty system honestly reports zeros — no placeholder statistics.
 */

import { Bar, Doughnut } from "react-chartjs-2";
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";

import { PageHeader } from "@/app/PageHeader";
import {
  Badge,
  Button,
  ErrorState,
  LoadingState,
  Metric,
  Panel,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/useApi";
import type { AdminDashboard } from "@/lib/types";

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

export function AdminDashboardPage() {
  const dashboard = useQuery(
    (signal) => api.get<AdminDashboard>("/admin/dashboard", undefined, signal),
    [],
  );

  if (dashboard.loading) return <LoadingState label="Loading system overview" />;
  if (dashboard.error) {
    return (
      <ErrorState
        message={dashboard.error.message}
        offline={dashboard.error.isOffline}
        onRetry={dashboard.refetch}
      />
    );
  }

  const data = dashboard.data;
  if (!data) return null;

  const hasScreenings = data.screenings.total > 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="System overview"
        subtitle="Live counts from the database."
        actions={<Button onClick={dashboard.refetch}>Refresh</Button>}
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total users" value={data.users.total} hint={`${data.users.active} active`} />
        <Metric label="Health workers" value={data.users.health_workers} />
        <Metric label="Doctors" value={data.users.doctors} />
        <Metric label="Patients" value={data.patients.total} />
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Screenings"
          value={data.screenings.total}
          hint={`${data.screenings.completed} completed`}
        />
        <Metric
          label="Pending reviews"
          value={data.reviews.pending}
          tone={data.reviews.pending > 0 ? "warn" : "neutral"}
        />
        <Metric
          label="Open referrals"
          value={data.referrals.pending}
          tone={data.referrals.pending > 0 ? "warn" : "neutral"}
        />
        <Metric
          label="Follow-ups due"
          value={data.follow_ups.due}
          tone={data.follow_ups.due > 0 ? "warn" : "neutral"}
        />
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel className="flex flex-col gap-4">
          <h2 className="rs-label">Screening pipeline</h2>
          {hasScreenings ? (
            <div style={{ height: 240 }}>
              <Bar
                data={{
                  labels: ["Completed", "In progress", "Captured offline"],
                  datasets: [
                    {
                      label: "Screenings",
                      data: [
                        data.screenings.completed,
                        data.screenings.in_progress,
                        data.screenings.captured_offline,
                      ],
                      backgroundColor: ["#2dd4bf", "#fbbf24", "#38bdf8"],
                      borderRadius: 6,
                    },
                  ],
                }}
                options={chartOptions}
              />
            </div>
          ) : (
            <EmptyChart message="No screenings recorded yet." />
          )}
        </Panel>

        <Panel className="flex flex-col gap-4">
          <h2 className="rs-label">Clinical review status</h2>
          {data.reviews.pending + data.reviews.in_review + data.reviews.completed > 0 ? (
            <div style={{ height: 240 }}>
              <Doughnut
                data={{
                  labels: ["Pending", "In review", "Completed"],
                  datasets: [
                    {
                      data: [
                        data.reviews.pending,
                        data.reviews.in_review,
                        data.reviews.completed,
                      ],
                      backgroundColor: ["#fb923c", "#38bdf8", "#2dd4bf"],
                      borderWidth: 0,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: { position: "bottom", labels: { color: "#9aa7b8" } },
                  },
                }}
              />
            </div>
          ) : (
            <EmptyChart message="No reviews recorded yet." />
          )}
        </Panel>
      </div>

      {/* Model status — reported honestly, never asserted. */}
      <Panel className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="rs-label">Screening model</h2>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={data.model.available ? "ok" : "danger"}>
              {data.model.available ? "Loaded" : "Unavailable"}
            </Badge>
            {data.model.is_development_model && (
              <Badge tone="warn">Development model</Badge>
            )}
            <Badge tone={data.model.clinically_validated ? "ok" : "warn"}>
              {data.model.clinically_validated
                ? "Clinically validated"
                : "Not clinically validated"}
            </Badge>
          </div>
        </div>

        <dl className="grid gap-3 sm:grid-cols-3">
          <Detail label="Version" value={data.model.model_version} />
          <Detail label="Framework" value={data.model.framework} />
          <Detail label="Source" value={data.model.source} />
        </dl>

        {data.model.is_development_model && (
          <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-warn)" }}>
            A development placeholder is active. Its output has no diagnostic
            meaning and must not be used clinically.
          </p>
        )}
      </Panel>

      {(data.sync.pending > 0 || data.sync.failed > 0) && (
        <Panel className="flex flex-wrap items-center gap-4">
          <h2 className="rs-label">Offline sync</h2>
          <span className="rs-numeric">{data.sync.pending} waiting</span>
          {data.sync.failed > 0 && (
            <span className="rs-numeric" style={{ color: "var(--rs-danger)" }}>
              {data.sync.failed} failed
            </span>
          )}
        </Panel>
      )}
    </div>
  );
}

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { ticks: { color: "#9aa7b8" }, grid: { display: false } },
    y: {
      ticks: { color: "#9aa7b8", precision: 0 },
      grid: { color: "rgba(154,167,184,0.14)" },
      beginAtZero: true,
    },
  },
} as const;

function EmptyChart({ message }: { message: string }) {
  return (
    <div
      className="flex h-[240px] items-center justify-center rounded-[var(--rs-radius-md)]"
      style={{ background: "var(--rs-surface-sunken)", color: "var(--rs-ink-subtle)" }}
    >
      {message}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="rs-label">{label}</dt>
      <dd className="rs-numeric text-[var(--rs-text-sm)]">{value}</dd>
    </div>
  );
}
