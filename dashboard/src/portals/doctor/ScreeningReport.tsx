/** Printable screening report — the browser's "Save as PDF" is the export. */

import { useParams } from "react-router-dom";

import { Button, ErrorState, LoadingState } from "@/design-system/components/primitives";
import { CATEGORY_LABELS } from "@/design-system/risk/RiskDisplay";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/useApi";
import type { ScreeningSessionDetail } from "@/lib/types";

export function ScreeningReport() {
  const { sessionId = "" } = useParams();
  const q = useQuery(
    (signal) => api.get<ScreeningSessionDetail>(`/screenings/${sessionId}`, undefined, signal),
    [sessionId],
  );
  if (q.loading) return <LoadingState label="Preparing report" />;
  if (q.error || !q.data) return <ErrorState message="Could not load this screening." onRetry={q.refetch} />;
  const s = q.data;

  return (
    <article className="rs-report mx-auto max-w-2xl bg-white p-8 text-black">
      <Button className="rs-no-print mb-6" variant="primary" onClick={() => window.print()}>
        Save as PDF
      </Button>
      <h1 className="text-2xl font-bold">RetinaSight AI screening report</h1>
      <p>{s.patient?.full_name} · {s.patient?.patient_code}</p>
      <p className="text-sm">Screened {new Date(s.completed_at ?? s.created_at).toLocaleString()}</p>

      <h2 className="mt-6 text-lg font-semibold">Findings</h2>
      <table className="w-full text-left text-sm">
        <thead><tr><th>Eye</th><th>Result</th><th>Confidence</th><th>Model</th></tr></thead>
        <tbody>
          {s.results.map((r) => (
            <tr key={r.id}>
              <td className="capitalize">{r.eye_side ?? "—"}</td>
              <td>{r.category ? CATEGORY_LABELS[r.category] : "—"}</td>
              <td>{Math.round((r.confidence ?? 0) * 100)}%</td>
              <td>{r.model_version}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {s.risk && (
        <>
          <h2 className="mt-6 text-lg font-semibold">Risk and next step</h2>
          <p className="capitalize">Risk level: {s.risk.risk_level}</p>
          <p>{s.risk.recommended_action}</p>
        </>
      )}

      <p className="mt-8 border-t pt-3 text-xs">
        This is AI-assisted screening support, not a diagnosis. Results must be confirmed by a
        qualified clinician. Not clinically validated.
      </p>
    </article>
  );
}
