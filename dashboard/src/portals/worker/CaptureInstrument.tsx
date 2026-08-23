/**
 * Guided retinal capture.
 *
 * This is intentionally not a file picker with a preview. It presents as a
 * dedicated screening instrument: an alignment reticle, live guidance for the
 * three things the operator can actually control (align / light / focus), and a
 * scanning indicator while the quality gate runs.
 *
 * The browser build accepts a device camera capture or an existing image; the
 * Flutter app drives the same backend flow with a live preview.
 */

import { useEffect, useRef, useState } from "react";

import { Button, Panel, cx } from "@/design-system/components/primitives";
import type { EyeSide, QualityAssessment } from "@/lib/types";

type Phase = "ready" | "captured" | "analysing" | "passed" | "failed";

interface Props {
  eyeSide: EyeSide;
  onCapture: (file: File) => Promise<void>;
  analysing: boolean;
  quality: QualityAssessment | null;
  /** Present when this eye already has an accepted capture. */
  accepted?: boolean;
  onRetake: () => void;
}

export function CaptureInstrument({
  eyeSide,
  onCapture,
  analysing,
  quality,
  accepted,
  onRetake,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("ready");

  useEffect(() => {
    if (analysing) setPhase("analysing");
    else if (quality) setPhase(quality.is_acceptable ? "passed" : "failed");
  }, [analysing, quality]);

  // Release the object URL when it is replaced or the component unmounts.
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(file);
    });
    setPhase("captured");
    await onCapture(file);
  };

  const eyeLabel = eyeSide === "left" ? "Left eye (OS)" : "Right eye (OD)";

  return (
    <Panel className="flex flex-col gap-4" padded>
      <header className="flex items-center justify-between gap-3">
        <div className="flex flex-col">
          <span className="rs-label">Capture</span>
          <h2 className="text-[var(--rs-text-lg)] font-bold">{eyeLabel}</h2>
        </div>
        {accepted && (
          <span
            className="inline-flex items-center gap-1.5 text-[var(--rs-text-xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
            style={{ color: "var(--rs-ok)" }}
          >
            <span aria-hidden="true">✓</span> Accepted
          </span>
        )}
      </header>

      {/* ---- viewfinder ---- */}
      <div
        className="relative overflow-hidden rounded-[var(--rs-radius-lg)]"
        style={{
          aspectRatio: "1 / 1",
          background: "radial-gradient(circle at 50% 50%, #141b23 0%, #05080c 78%)",
          border: "1px solid var(--rs-line)",
          boxShadow: "var(--rs-shadow-sunken)",
        }}
      >
        {preview ? (
          <img
            src={preview}
            alt={`Captured retinal image, ${eyeLabel}`}
            className="h-full w-full object-cover"
            style={{ opacity: phase === "analysing" ? 0.75 : 1 }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <span className="text-[var(--rs-text-sm)]" style={{ color: "#6d7d91" }}>
              Align the lens with the pupil
            </span>
          </div>
        )}

        {/* Alignment reticle — the framing target for the operator. */}
        <svg
          viewBox="0 0 200 200"
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden="true"
        >
          <circle
            cx="100"
            cy="100"
            r="72"
            fill="none"
            stroke={phase === "failed" ? "var(--rs-danger)" : "var(--rs-accent)"}
            strokeWidth="1.4"
            strokeDasharray="5 6"
            opacity="0.8"
          />
          <circle
            cx="100"
            cy="100"
            r="30"
            fill="none"
            stroke="var(--rs-accent)"
            strokeWidth="0.9"
            opacity="0.45"
          />
          {[
            "M100 16 v14", "M100 170 v14", "M16 100 h14", "M170 100 h14",
          ].map((d) => (
            <path key={d} d={d} stroke="var(--rs-accent)" strokeWidth="1.6" opacity="0.75" />
          ))}
        </svg>

        {/* Scanning sweep while the quality gate runs. */}
        {phase === "analysing" && (
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            <div
              className="absolute inset-x-0 h-1/3"
              style={{
                background:
                  "linear-gradient(180deg, transparent, color-mix(in srgb, var(--rs-accent) 45%, transparent), transparent)",
                animation: "rs-scan 1.4s var(--rs-ease) infinite",
              }}
            />
          </div>
        )}

        <span
          className="absolute left-3 top-3 rounded-[var(--rs-radius-xs)] px-2 py-1 text-[var(--rs-text-2xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
          style={{ background: "rgba(0,0,0,0.6)", color: "#dce6f2" }}
        >
          {eyeLabel}
        </span>
      </div>

      {/* ---- instrument readouts ---- */}
      <div className="grid grid-cols-3 gap-2">
        <Readout
          label="Align"
          score={quality?.framing_score}
          active={phase === "analysing"}
        />
        <Readout
          label="Light"
          score={quality?.lighting_score}
          active={phase === "analysing"}
        />
        <Readout label="Focus" score={quality?.blur_score} active={phase === "analysing"} />
      </div>

      {/* ---- quality verdict ---- */}
      {phase === "failed" && quality && (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-[var(--rs-radius-md)] border p-3"
          style={{
            borderColor: "color-mix(in srgb, var(--rs-danger) 45%, transparent)",
            background: "color-mix(in srgb, var(--rs-danger) 8%, transparent)",
          }}
        >
          <p
            className="text-[var(--rs-text-xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
            style={{ color: "var(--rs-danger)" }}
          >
            Image not suitable for analysis
          </p>
          {quality.recommendations.length > 0 && (
            <ul className="flex list-disc flex-col gap-1 pl-5 text-[var(--rs-text-sm)]">
              {quality.recommendations.map((tip) => (
                <li key={tip}>{tip}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {phase === "passed" && quality && (
        <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ok)" }}>
          <span aria-hidden="true">✓ </span>
          Image quality accepted ({Math.round(quality.overall_score * 100)}%).
        </p>
      )}

      {/* ---- capture control ---- */}
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        className="sr-only"
        onChange={(event) => void handleFile(event.target.files?.[0])}
        aria-label={`Capture retinal image for ${eyeLabel}`}
      />

      <div className="flex flex-wrap gap-2">
        <Button
          variant="primary"
          size="lg"
          className="flex-1"
          loading={analysing}
          onClick={() => inputRef.current?.click()}
        >
          {phase === "ready" ? "Capture" : "Capture again"}
        </Button>
        {phase === "failed" && (
          <Button variant="secondary" size="lg" onClick={onRetake}>
            Retake
          </Button>
        )}
      </div>
    </Panel>
  );
}

/** A single instrument readout: bar + numeric value + label. */
function Readout({
  label,
  score,
  active,
}: {
  label: string;
  score?: number;
  active?: boolean;
}) {
  const percent = score === undefined ? null : Math.round(score * 100);
  const tone =
    percent === null
      ? "var(--rs-ink-subtle)"
      : percent >= 70
        ? "var(--rs-ok)"
        : percent >= 45
          ? "var(--rs-warn)"
          : "var(--rs-danger)";

  return (
    <div className="rs-inset flex flex-col items-center gap-1.5 p-2.5">
      <span className="rs-label">{label}</span>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full"
        style={{ background: "color-mix(in srgb, var(--rs-ink) 12%, transparent)" }}
      >
        <div
          className={cx("h-full rounded-full transition-all duration-[var(--rs-duration-slow)]")}
          style={{
            width: percent === null ? (active ? "40%" : "0%") : `${percent}%`,
            background: tone,
            opacity: active && percent === null ? 0.6 : 1,
          }}
        />
      </div>
      <span className="rs-numeric text-[var(--rs-text-xs)] font-semibold" style={{ color: tone }}>
        {percent === null ? (active ? "···" : "—") : `${percent}%`}
      </span>
    </div>
  );
}
