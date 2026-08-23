/**
 * Risk queue.
 *
 * Ordered by the configured risk engine (most urgent first, oldest first within
 * a band) — not by arrival time, and not by anything the UI invents.
 */

import { useState } from "react";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Panel,
  Select,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/useApi";
import type { Page, RiskQueueItem } from "@/lib/types";
import { CaseRow } from "./DoctorDashboard";

export function RiskQueue() {
  const [status, setStatus] = useState("pending");
  const [riskLevel, setRiskLevel] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [search, setSearch] = useState("");

  const queue = useQuery(
    (signal) =>
      api.get<Page<RiskQueueItem>>(
        "/reviews/queue",
        {
          status: status || undefined,
          risk_level: riskLevel || undefined,
          mine_only: mineOnly,
          page_size: 100,
        },
        signal,
      ),
    [status, riskLevel, mineOnly],
  );

  const term = search.trim().toLowerCase();
  const items = (queue.data?.items ?? []).filter(
    (item) =>
      !term ||
      item.patient.full_name.toLowerCase().includes(term) ||
      item.patient.patient_code.toLowerCase().includes(term),
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Risk queue"
        subtitle="Ordered by clinical urgency, then by how long a case has waited."
        actions={<Button onClick={queue.refetch}>Refresh</Button>}
      />

      <Panel className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Search patient" htmlFor="q">
          <Input
            id="q"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name or code"
          />
        </Field>
        <Field label="Review status" htmlFor="status">
          <Select id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="pending">Pending</option>
            <option value="in_review">In review</option>
            <option value="completed">Completed</option>
            <option value="">All</option>
          </Select>
        </Field>
        <Field label="Risk band" htmlFor="risk">
          <Select id="risk" value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)}>
            <option value="">All bands</option>
            <option value="urgent">Urgent</option>
            <option value="high">High</option>
            <option value="moderate">Moderate</option>
            <option value="low">Low</option>
          </Select>
        </Field>
        <Field label="Assignment" htmlFor="mine">
          <Select
            id="mine"
            value={mineOnly ? "mine" : "all"}
            onChange={(e) => setMineOnly(e.target.value === "mine")}
          >
            <option value="all">All clinicians</option>
            <option value="mine">Claimed by me</option>
          </Select>
        </Field>
      </Panel>

      {queue.loading && <LoadingState label="Loading queue" />}
      {queue.error && (
        <ErrorState
          message={queue.error.message}
          offline={queue.error.isOffline}
          onRetry={queue.refetch}
        />
      )}

      {queue.data && items.length === 0 && (
        <EmptyState
          title="No cases match"
          description="Try widening the filters, or check back later."
        />
      )}

      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <CaseRow key={item.review.id} item={item} />
        ))}
      </div>

      {queue.data && items.length > 0 && (
        <p className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
          Showing {items.length} of {queue.data.total} case
          {queue.data.total === 1 ? "" : "s"}.
        </p>
      )}
    </div>
  );
}
