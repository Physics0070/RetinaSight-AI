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

import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Panel, cx } from "@/design-system/components/primitives";
import type { EyeSide, QualityAssessment } from "@/lib/types";

type Phase = "ready" | "captured" | "analysing" | "passed" | "failed";

// A phone photo often frames the fundus too small or off-centre. Zoom + pan let
// the operator fit it inside the reticle before the quality gate runs.
const ZOOM_MIN = 1;
const ZOOM_MAX = 5;
const ZOOM_STEP = 0.3;

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

  // Framing transform for the captured preview.
  const [zoom, setZoom] = useState(ZOOM_MIN);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragState = useRef<{ x: number; y: number; active: boolean }>({
    x: 0,
    y: 0,
    active: false,
  });

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

  const resetView = useCallback(() => {
    setZoom(ZOOM_MIN);
    setOffset({ x: 0, y: 0 });
  }, []);

  const changeZoom = useCallback((delta: number) => {
    setZoom((current) => {
      const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((current + delta).toFixed(2))));
      if (next === ZOOM_MIN) setOffset({ x: 0, y: 0 });
      return next;
    });
  }, []);

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!preview || zoom === ZOOM_MIN) return;
    dragState.current = { x: event.clientX, y: event.clientY, active: true };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragState.current.active) return;
    const dx = event.clientX - dragState.current.x;
    const dy = event.clientY - dragState.current.y;
    dragState.current = { x: event.clientX, y: event.clientY, active: true };
    setOffset((current) => ({ x: current.x + dx, y: current.y + dy }));
  };
  const endDrag = () => {
    dragState.current.active = false;
  };

  // Keyboard parity — a mouse must never be required to frame the image.
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!preview) return;
    const nudge = 20;
    const actions: Record<string, () => void> = {
      "+": () => changeZoom(ZOOM_STEP),
      "=": () => changeZoom(ZOOM_STEP),
      "-": () => changeZoom(-ZOOM_STEP),
      "0": resetView,
      ArrowUp: () => setOffset((c) => ({ ...c, y: c.y + nudge })),
      ArrowDown: () => setOffset((c) => ({ ...c, y: c.y - nudge })),
      ArrowLeft: () => setOffset((c) => ({ ...c, x: c.x + nudge })),
      ArrowRight: () => setOffset((c) => ({ ...c, x: c.x - nudge })),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(file);
    });
    resetView();
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
        role={preview ? "group" : undefined}
        aria-label={
          preview
            ? `Captured ${eyeLabel} image. Use plus and minus to zoom, arrow keys to pan, zero to fit.`
            : undefined
        }
        tabIndex={preview ? 0 : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
        onKeyDown={onKeyDown}
        className="relative overflow-hidden rounded-[var(--rs-radius-lg)] outline-none"
        style={{
          aspectRatio: "1 / 1",
          background: "radial-gradient(circle at 50% 50%, #141b23 0%, #05080c 78%)",
          boxShadow: "var(--rs-shadow-sunken)",
          cursor: preview && zoom > ZOOM_MIN ? "grab" : "default",
          touchAction: "none",
        }}
      >
        {preview ? (
          <img
            src={preview}
            alt={`Captured retinal image, ${eyeLabel}`}
            draggable={false}
            className="h-full w-full select-none object-contain"
            style={{
              opacity: phase === "analysing" ? 0.75 : 1,
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
              transition: dragState.current.active
                ? "none"
                : "transform var(--rs-duration) var(--rs-ease)",
            }}
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

        {preview && zoom > ZOOM_MIN && (
          <span
            className="rs-numeric pointer-events-none absolute right-3 top-3 rounded-[var(--rs-radius-xs)] px-2 py-1 text-[var(--rs-text-2xs)]"
            style={{ background: "rgba(0,0,0,0.6)", color: "#dce6f2" }}
          >
            {zoom.toFixed(1)}×
          </span>
        )}
      </div>

      {/* ---- framing controls (once an image is captured) ---- */}
      {preview && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="rs-label mr-1">Fit to frame</span>
          <ZoomButton onClick={() => changeZoom(ZOOM_STEP)} label="Zoom in" disabled={zoom >= ZOOM_MAX}>
            +
          </ZoomButton>
          <ZoomButton onClick={() => changeZoom(-ZOOM_STEP)} label="Zoom out" disabled={zoom <= ZOOM_MIN}>
            −
          </ZoomButton>
          <ZoomButton onClick={resetView} label="Fit to view" disabled={zoom === ZOOM_MIN && offset.x === 0 && offset.y === 0}>
            Fit
          </ZoomButton>
          <span className="text-[var(--rs-text-2xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
            Drag or use arrow keys to reposition
          </span>
        </div>
      )}

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

/** A compact neumorphic control for the framing toolbar. */
function ZoomButton({
  children,
  onClick,
  label,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      disabled={disabled}
      className="rs-neu min-w-[2.5rem] rounded-[var(--rs-radius-md)] px-3 py-1.5 text-[var(--rs-text-sm)] font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
      style={{ background: "var(--rs-surface-raised)", color: "var(--rs-ink)" }}
    >
      {children}
    </button>
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
