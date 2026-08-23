/**
 * Case review workstation.
 *
 * Layout intent: the retinal image dominates; AI output sits beside it as
 * evidence, clearly framed as decision support; the clinician's own judgement
 * is what gets recorded. Exits (release, back to queue) are always available.
 */

import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  ErrorState,
  Field,
  LoadingState,
  Panel,
  Select,
  Textarea,
} from "@/design-system/components/primitives";
import {
  RetinalImageViewer,
  type RetinalImageSource,
} from "@/design-system/medical-imaging/RetinalImageViewer";
import {
  AiAssistanceNotice,
  CATEGORY_LABELS,
  ConfidenceMeter,
  DevelopmentModelBanner,
  RiskBadge,
  RiskScale,
} from "@/design-system/risk/RiskDisplay";
import { api } from "@/lib/api";
import { useMutation, useQuery } from "@/lib/useApi";
import type {
  ClinicalReview,
  Explanation,
  Patient,
  RetinalImageWithUrl,
  ScreeningCategory,
  ScreeningSessionDetail,
} from "@/lib/types";

const DECISIONS = [
  { value: "confirm_ai", label: "Confirm the screening result" },
  { value: "revise", label: "Revise the grading" },
  { value: "refer", label: "Refer for specialist care" },
  { value: "routine_follow_up", label: "Routine follow-up" },
  { value: "dismiss", label: "No action needed" },
] as const;

export function CaseReview() {
  const { reviewId } = useParams<{ reviewId: string }>();
  const navigate = useNavigate();

  const review = useQuery(
    (signal) => api.get<ClinicalReview>(`/reviews/${reviewId}`, undefined, signal),
    [reviewId],
  );

  const sessionId = review.data?.session_id;

  const session = useQuery(
    (signal) =>
      sessionId
        ? api.get<ScreeningSessionDetail>(`/screenings/${sessionId}`, undefined, signal)
        : Promise.resolve(null),
    [sessionId],
  );
  const images = useQuery(
    (signal) =>
      sessionId
        ? api.get<RetinalImageWithUrl[]>(
            `/images/session/${sessionId}`,
            { active_only: true },
            signal,
          )
        : Promise.resolve([]),
    [sessionId],
  );
  const explanations = useQuery(
    (signal) =>
      sessionId
        ? api.get<Explanation[]>(`/screenings/${sessionId}/explanations`, undefined, signal)
        : Promise.resolve([]),
    [sessionId],
  );

  const [decision, setDecision] = useState<string>("confirm_ai");
  const [category, setCategory] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [followUpNotes, setFollowUpNotes] = useState("");

  const claim = useMutation(async () => {
    await api.post(`/reviews/${reviewId}/claim`);
    review.refetch();
  });

  const release = useMutation(async () => {
    await api.post(`/reviews/${reviewId}/release`);
    navigate("/doctor/risk-queue");
  });

  const complete = useMutation(async () => {
    await api.post(`/reviews/${reviewId}/complete`, {
      decision,
      clinician_category: category || null,
      notes: notes.trim() || null,
      follow_up_due: followUpDate || null,
      follow_up_instructions: followUpNotes.trim() || null,
    });
    navigate("/doctor/risk-queue");
  });

  // Pair each active image with its explanation for the viewer.
  const sources = useMemo<RetinalImageSource[]>(() => {
    const list = images.data ?? [];
    const results = session.data?.results ?? [];
    const explanationList = explanations.data ?? [];

    return list.map((image) => {
      const result = results.find((r) => r.image_id === image.id);
      const explanation = result
        ? explanationList.find((e) => e.inference_result_id === result.id)
        : undefined;
      return {
        eyeSide: image.eye_side,
        originalUrl: image.url,
        heatmapUrl: explanation?.heatmap_url ?? null,
        overlayUrl: explanation?.overlay_url ?? null,
        affectedRegions: explanation?.affected_regions,
        capturedAt: image.created_at,
      };
    });
  }, [images.data, session.data?.results, explanations.data]);

  if (review.loading) return <LoadingState label="Loading case" />;
  if (review.error) {
    return (
      <ErrorState
        message={review.error.message}
        offline={review.error.isOffline}
        onRetry={review.refetch}
      />
    );
  }

  const detail = session.data;
  const worst = detail?.results.reduce<typeof detail.results[number] | null>((acc, current) => {
    if (!current.category) return acc;
    if (!acc) return current;
    const order = ["no_dr", "mild", "moderate", "severe", "proliferative"];
    return order.indexOf(current.category) > order.indexOf(acc.category ?? "no_dr")
      ? current
      : acc;
  }, null);

  const alreadyReviewed = review.data?.status === "completed";
  const patient: Patient | null = detail?.patient ?? null;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={patient ? patient.full_name : "Case review"}
        subtitle={
          patient
            ? `${patient.patient_code}${patient.has_diabetes ? " · Diabetes recorded" : ""}`
            : undefined
        }
        backTo="/doctor/risk-queue"
        backLabel="Risk queue"
        actions={
          <>
            {!alreadyReviewed && review.data?.status !== "in_review" && (
              <Button loading={claim.loading} onClick={() => void claim.run()}>
                Claim case
              </Button>
            )}
            {!alreadyReviewed && (
              <Button variant="ghost" loading={release.loading} onClick={() => void release.run()}>
                Exit without deciding
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* ---- imaging column ---- */}
        <section className="flex flex-col gap-4">
          {images.loading && <LoadingState label="Loading retinal images" />}
          {sources.length === 0 && !images.loading && (
            <Panel>
              <p style={{ color: "var(--rs-ink-muted)" }}>
                No retinal images are available for this screening.
              </p>
            </Panel>
          )}
          {sources.map((source, index) => (
            <RetinalImageViewer
              key={`${source.eyeSide}-${index}`}
              image={source}
              comparisonImage={sources.find((s) => s.eyeSide !== source.eyeSide) ?? null}
            />
          ))}
        </section>

        {/* ---- evidence + decision column ---- */}
        <section className="flex flex-col gap-4">
          {worst?.is_development_model && <DevelopmentModelBanner />}

          <Panel className="flex flex-col gap-4">
            <h2 className="rs-label">AI-assisted screening</h2>

            <div className="flex flex-col gap-1">
              <span className="rs-label">Screening category</span>
              <span className="text-[var(--rs-text-xl)] font-bold">
                {worst?.category ? CATEGORY_LABELS[worst.category] : "Not classified"}
              </span>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="rs-label">Model confidence</span>
              <ConfidenceMeter value={worst?.confidence ?? null} />
            </div>

            <dl className="grid grid-cols-2 gap-3 text-[var(--rs-text-xs)]">
              <MetaItem label="Model version" value={worst?.model_version ?? "—"} />
              <MetaItem label="Inference mode" value={worst?.inference_mode ?? "—"} />
              <MetaItem
                label="Image quality"
                value={
                  detail?.quality.every((q) => q.is_acceptable)
                    ? "Acceptable"
                    : "Limited"
                }
              />
              <MetaItem label="Eyes screened" value={String(detail?.results.length ?? 0)} />
            </dl>

            <AiAssistanceNotice />
          </Panel>

          {detail?.risk && (
            <Panel className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="rs-label">Risk assessment</h2>
                <RiskBadge level={detail.risk.risk_level} />
              </div>
              <RiskScale level={detail.risk.risk_level} />
              <div className="flex flex-col gap-1">
                <p className="text-[var(--rs-text-sm)] font-medium">
                  {detail.risk.recommended_action}
                </p>
                <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
                  {detail.risk.reason}
                </p>
              </div>
              {detail.referral && (
                <p className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
                  Referral raised at <strong>{detail.referral.priority}</strong> priority.
                </p>
              )}
            </Panel>
          )}

          {/* ---- clinical decision ---- */}
          {alreadyReviewed ? (
            <Panel className="flex flex-col gap-2">
              <h2 className="rs-label">Review complete</h2>
              <p className="text-[var(--rs-text-sm)]">
                Decision: <strong>{review.data?.decision?.replace(/_/g, " ")}</strong>
              </p>
              {review.data?.notes && (
                <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
                  {review.data.notes}
                </p>
              )}
              <Button variant="secondary" onClick={() => navigate("/doctor/risk-queue")}>
                Return to queue
              </Button>
            </Panel>
          ) : (
            <Panel className="flex flex-col gap-4">
              <h2 className="rs-label">Your clinical decision</h2>

              <Field label="Decision" htmlFor="decision" required>
                <Select
                  id="decision"
                  value={decision}
                  onChange={(e) => setDecision(e.target.value)}
                >
                  {DECISIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field
                label="Your grading"
                htmlFor="category"
                hint="Recorded alongside the AI result so agreement can be tracked."
              >
                <Select
                  id="category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="">Not specified</option>
                  {(Object.keys(CATEGORY_LABELS) as ScreeningCategory[]).map((key) => (
                    <option key={key} value={key}>
                      {CATEGORY_LABELS[key]}
                    </option>
                  ))}
                </Select>
              </Field>

              <Field label="Clinical notes" htmlFor="notes">
                <Textarea
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Findings, reasoning, and anything the health worker should know."
                />
              </Field>

              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Follow-up date" htmlFor="follow-up">
                  <input
                    id="follow-up"
                    type="date"
                    value={followUpDate}
                    onChange={(e) => setFollowUpDate(e.target.value)}
                    className="w-full rounded-[var(--rs-radius-md)] border px-3 py-2.5 text-[var(--rs-text-sm)]"
                    style={{
                      background: "var(--rs-surface-sunken)",
                      borderColor: "var(--rs-line)",
                      color: "var(--rs-ink)",
                    }}
                  />
                </Field>
                <Field label="Follow-up instructions" htmlFor="follow-up-notes">
                  <input
                    id="follow-up-notes"
                    value={followUpNotes}
                    onChange={(e) => setFollowUpNotes(e.target.value)}
                    className="w-full rounded-[var(--rs-radius-md)] border px-3 py-2.5 text-[var(--rs-text-sm)]"
                    style={{
                      background: "var(--rs-surface-sunken)",
                      borderColor: "var(--rs-line)",
                      color: "var(--rs-ink)",
                    }}
                  />
                </Field>
              </div>

              {complete.error && <ErrorState message={complete.error.message} />}

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  size="lg"
                  loading={complete.loading}
                  onClick={() => void complete.run()}
                >
                  Complete review
                </Button>
                <Button variant="ghost" onClick={() => navigate("/doctor/risk-queue")}>
                  Back to queue
                </Button>
              </div>
            </Panel>
          )}
        </section>
      </div>
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="rs-label">{label}</dt>
      <dd className="rs-numeric" style={{ color: "var(--rs-ink)" }}>
        {value}
      </dd>
    </div>
  );
}
