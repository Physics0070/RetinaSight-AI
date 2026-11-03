/** Grade-over-time and side-by-side visit comparison for one patient. */

import { useState } from "react";

import { Badge, Panel, Select } from "@/design-system/components/primitives";
import { CATEGORY_LABELS, RiskBadge } from "@/design-system/risk/RiskDisplay";
import { api } from "@/lib/api";
import { trendOf, visitGrade, worstResult } from "@/lib/trend";
import { useQuery } from "@/lib/useApi";
import type { Page, ScreeningSession, ScreeningSessionDetail } from "@/lib/types";

const MAX_VISITS = 8;
const TONE = { worsening: "danger", improving: "ok", stable: "info", insufficient: "neutral" } as const;

const day = (s: ScreeningSessionDetail) =>
  new Date(s.completed_at ?? s.created_at).toLocaleDateString();

export function PatientTrend({ patientId }: { patientId: string }) {
  const visits = useQuery(async (signal) => {
    const page = await api.get<Page<ScreeningSession>>(
      "/screenings",
      { patient_id: patientId, page_size: MAX_VISITS },
      signal,
    );
    const details = await Promise.all(
      page.items.map((s) => api.get<ScreeningSessionDetail>(`/screenings/${s.id}`, undefined, signal)),
    );
    // API is newest-first; the chart reads oldest-first.
    return details.filter((d) => visitGrade(d) !== null).reverse();
  }, [patientId]);

  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);

  const list = visits.data ?? [];
  if (visits.loading || list.length === 0) return null;

  const grades = list.map(visitGrade);
  const trend = trendOf(grades);
  const from = list.find((v) => v.id === a) ?? list[Math.max(list.length - 2, 0)];
  const to = list.find((v) => v.id === b) ?? list[list.length - 1];

  const w = 240, h = 56, step = list.length > 1 ? w / (list.length - 1) : 0;
  const points = grades.map((g, i) => `${i * step},${h - 4 - ((g ?? 0) / 4) * (h - 8)}`).join(" ");

  return (
    <Panel>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Screening trend</h2>
        <Badge tone={TONE[trend]}>{trend === "insufficient" ? "Need 2+ visits" : trend}</Badge>
      </div>
      {list.length < 2 && (
        <p className="mt-2 text-sm opacity-70">Only one screening so far — a trend appears after the next visit.</p>
      )}
      {list.length > 1 && (
        <>
          <svg role="img" aria-label="Retinopathy grade over time" viewBox={`0 0 ${w} ${h}`} className="mt-3 w-full max-w-md">
            <polyline fill="none" stroke="var(--rs-accent, #0e7c86)" strokeWidth="2" points={points} />
            {grades.map((g, i) => (
              <circle key={list[i].id} cx={i * step} cy={h - 4 - ((g ?? 0) / 4) * (h - 8)} r="3" fill="var(--rs-accent, #0e7c86)" />
            ))}
          </svg>
          <p className="text-xs opacity-70">Grade 0 (no DR) to 4 (proliferative), oldest to newest.</p>
        </>
      )}

      {list.length > 1 && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {([[from, setA, "Earlier visit"], [to, setB, "Later visit"]] as const).map(([v, set, label]) => {
            const worst = worstResult(v.results);
            return (
              <div key={label} className="rs-inset p-3">
                <label className="text-xs font-semibold">
                  {label}
                  <Select value={v.id} onChange={(e) => set(e.target.value)}>
                    {list.map((o) => (
                      <option key={o.id} value={o.id}>{day(o)}</option>
                    ))}
                  </Select>
                </label>
                <p className="mt-2 font-semibold">{CATEGORY_LABELS[worst!.category!]}</p>
                <p className="text-xs">Confidence {Math.round((worst!.confidence ?? 0) * 100)}%</p>
                {v.risk && <RiskBadge level={v.risk.risk_level} />}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
