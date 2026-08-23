/**
 * The screening workflow loop.
 *
 * Drives the backend state machine: capture → quality gate → (retake) →
 * inference → risk → referral → submit for review. The current state comes from
 * the server, so a refresh, a lost connection, or a different device all resume
 * at the same point.
 *
 * Exit points are present at every step: Save & exit, Cancel, and Back.
 */

import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  ErrorState,
  LoadingState,
  Panel,
} from "@/design-system/components/primitives";
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
  CaptureResponse,
  EyeSide,
  InferenceRunResponse,
  QualityAssessment,
  Referral,
  ScreeningSessionDetail,
} from "@/lib/types";
import { CaptureInstrument } from "./CaptureInstrument";
import { ScreeningStateChip } from "./ScreeningStateChip";

export function ScreeningWorkflow() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [activeEye, setActiveEye] = useState<EyeSide>("left");
  const [lastQuality, setLastQuality] = useState<Record<EyeSide, QualityAssessment | null>>({
    left: null,
    right: null,
  });
  const [inference, setInference] = useState<InferenceRunResponse | null>(null);
  const [referral, setReferral] = useState<Referral | null>(null);

  const session = useQuery(
    (signal) =>
      api.get<ScreeningSessionDetail>(`/screenings/${sessionId}`, undefined, signal),
    [sessionId],
  );

  const capture = useMutation(async (file: File, eye: EyeSide) => {
    const form = new FormData();
    form.append("file", file);
    form.append("eye_side", eye);
    const response = await api.upload<CaptureResponse>(
      `/screenings/${sessionId}/capture`,
      form,
    );
    setLastQuality((current) => ({ ...current, [eye]: response.quality }));
    session.refetch();
    return response;
  });

  const runScreening = useMutation(async () => {
    const response = await api.post<InferenceRunResponse>(
      `/screenings/${sessionId}/inference`,
    );
    setInference(response);
    session.refetch();
    return response;
  });

  const createReferral = useMutation(async () => {
    const response = await api.post<Referral | null>(`/screenings/${sessionId}/referral`);
    setReferral(response);
    session.refetch();
    return response;
  });

  const submitReview = useMutation(async () => {
    await api.post(`/screenings/${sessionId}/submit-review`);
    session.refetch();
  });

  const cancel = useMutation(async (reason: string) => {
    await api.post(`/screenings/${sessionId}/cancel`, { reason });
    navigate("/user/dashboard");
  });

  const handleCapture = useCallback(
    async (file: File) => {
      await capture.run(file, activeEye);
    },
    [capture, activeEye],
  );

  if (session.loading && !session.data) return <LoadingState label="Loading screening" />;
  if (session.error) {
    return (
      <ErrorState
        message={session.error.message}
        offline={session.error.isOffline}
        onRetry={session.refetch}
      />
    );
  }

  const detail = session.data;
  if (!detail) return null;

  const qualityFor = (eye: EyeSide): QualityAssessment | null => {
    const image = detail.images.find((i) => i.eye_side === eye && i.is_active);
    if (!image) return lastQuality[eye];
    return detail.quality.find((q) => q.image_id === image.id) ?? lastQuality[eye];
  };

  const leftAccepted = qualityFor("left")?.is_acceptable ?? false;
  const rightAccepted = qualityFor("right")?.is_acceptable ?? false;
  const canScreen = leftAccepted || rightAccepted;
  const risk = inference?.risk ?? detail.risk;
  const worst = inference?.worst ?? detail.results.at(-1) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Screening"
        subtitle={detail.patient ? `${detail.patient.full_name} · ${detail.patient.patient_code}` : undefined}
        backTo="/user/dashboard"
        backLabel="Dashboard"
        actions={
          <>
            <Button
              variant="ghost"
              onClick={() => navigate("/user/dashboard")}
              title="Your progress is saved; you can resume this screening later."
            >
              Save &amp; exit
            </Button>
            {!detail.is_terminal && (
              <Button
                variant="ghost"
                loading={cancel.loading}
                onClick={() => void cancel.run("Cancelled by health worker")}
              >
                Cancel screening
              </Button>
            )}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <ScreeningStateChip state={detail.state} />
        {detail.captured_offline && (
          <span className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-warn)" }}>
            Captured offline · will sync automatically
          </span>
        )}
      </div>

      {/* ---- Step 1: capture ---- */}
      {!detail.is_terminal && (
        <section className="flex flex-col gap-3">
          <StepHeading step={1} title="Capture both eyes" />

          <div
            role="group"
            aria-label="Select eye"
            className="inline-flex overflow-hidden rounded-[var(--rs-radius-md)] border"
            style={{ borderColor: "var(--rs-line)", width: "fit-content" }}
          >
            {(["left", "right"] as EyeSide[]).map((eye) => {
              const isActive = activeEye === eye;
              const done = eye === "left" ? leftAccepted : rightAccepted;
              return (
                <button
                  key={eye}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => setActiveEye(eye)}
                  className="px-4 py-2 text-[var(--rs-text-sm)] font-semibold"
                  style={{
                    background: isActive ? "var(--rs-accent)" : "var(--rs-surface-raised)",
                    color: isActive ? "var(--rs-accent-ink)" : "var(--rs-ink-muted)",
                  }}
                >
                  {done && <span aria-hidden="true">✓ </span>}
                  {eye === "left" ? "Left eye" : "Right eye"}
                </button>
              );
            })}
          </div>

          <CaptureInstrument
            eyeSide={activeEye}
            onCapture={handleCapture}
            analysing={capture.loading}
            quality={qualityFor(activeEye)}
            accepted={activeEye === "left" ? leftAccepted : rightAccepted}
            onRetake={() => setLastQuality((c) => ({ ...c, [activeEye]: null }))}
          />

          {capture.error && (
            <ErrorState
              message={capture.error.message}
              offline={capture.error.isOffline}
            />
          )}
        </section>
      )}

      {/* ---- Step 2: run screening ---- */}
      {canScreen && !detail.is_terminal && (
        <section className="flex flex-col gap-3">
          <StepHeading step={2} title="Run AI screening" />
          <Panel className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
              {leftAccepted && rightAccepted
                ? "Both eyes passed the quality gate."
                : "One eye passed the quality gate. You can screen now or capture the other eye."}
            </p>
            <Button
              variant="primary"
              size="lg"
              loading={runScreening.loading}
              onClick={() => void runScreening.run()}
            >
              {inference ? "Run again" : "Run screening"}
            </Button>
          </Panel>
          {runScreening.error && <ErrorState message={runScreening.error.message} />}
        </section>
      )}

      {/* ---- Step 3: result ---- */}
      {worst && (
        <section className="flex flex-col gap-3">
          <StepHeading step={3} title="Result" />

          {worst.is_development_model && <DevelopmentModelBanner />}

          <Panel className="flex flex-col gap-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex flex-col gap-1">
                <span className="rs-label">Screening category</span>
                <span className="text-[var(--rs-text-xl)] font-bold">
                  {worst.category ? CATEGORY_LABELS[worst.category] : "Not classified"}
                </span>
              </div>
              {risk && <RiskBadge level={risk.risk_level} />}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <span className="rs-label">Model confidence</span>
                <ConfidenceMeter value={worst.confidence} />
              </div>
              {risk && (
                <div className="flex flex-col gap-1.5">
                  <span className="rs-label">Risk band</span>
                  <RiskScale level={risk.risk_level} />
                </div>
              )}
            </div>

            {risk && (
              <div className="rs-inset flex flex-col gap-1 p-3">
                <span className="rs-label">Recommended action</span>
                <p className="text-[var(--rs-text-sm)] font-medium">{risk.recommended_action}</p>
                <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
                  {risk.reason}
                </p>
              </div>
            )}

            <AiAssistanceNotice />
          </Panel>
        </section>
      )}

      {/* ---- Step 4: referral + handoff ---- */}
      {risk && !detail.is_terminal && (
        <section className="flex flex-col gap-3">
          <StepHeading step={4} title="Referral and review" />
          <Panel className="flex flex-col gap-3">
            {(referral ?? detail.referral) ? (
              <p className="text-[var(--rs-text-sm)]">
                <span aria-hidden="true">✓ </span>
                Referral created with{" "}
                <strong>{(referral ?? detail.referral)?.priority}</strong> priority.
              </p>
            ) : (
              <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
                {risk.risk_level === "low"
                  ? "This risk band does not require a referral, but a clinician still reviews the screening."
                  : "Create a referral so a clinician can review this case."}
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              {!(referral ?? detail.referral) && risk.risk_level !== "low" && (
                <Button
                  variant="primary"
                  loading={createReferral.loading}
                  onClick={() => void createReferral.run()}
                >
                  Create referral
                </Button>
              )}
              <Button
                variant="secondary"
                loading={submitReview.loading}
                onClick={() => void submitReview.run()}
              >
                Send for clinical review
              </Button>
              <Button variant="ghost" onClick={() => navigate("/user/dashboard")}>
                Done for now
              </Button>
            </div>
          </Panel>
        </section>
      )}

      {detail.is_terminal && (
        <Panel className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-semibold">This screening is {detail.state_label.toLowerCase()}.</p>
          <Button variant="secondary" onClick={() => navigate("/user/screenings")}>
            Back to screenings
          </Button>
        </Panel>
      )}
    </div>
  );
}

function StepHeading({ step, title }: { step: number; title: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className="rs-numeric flex h-6 w-6 items-center justify-center rounded-full text-[var(--rs-text-xs)] font-bold"
        style={{ background: "var(--rs-accent)", color: "var(--rs-accent-ink)" }}
        aria-hidden="true"
      >
        {step}
      </span>
      <h2 className="text-[var(--rs-text-lg)] font-semibold">{title}</h2>
    </div>
  );
}
