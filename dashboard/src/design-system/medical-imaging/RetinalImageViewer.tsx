/**
 * Retinal image viewer — the visual centre of the clinical workspace.
 *
 * Behaves like a medical imaging workstation rather than a web gallery: the
 * image sits on a deep neutral ground, chrome stays out of the way, and the
 * clinician controls what is layered on top (original / heatmap / overlay),
 * with zoom, pan and a side-by-side comparison.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { cx } from "@/design-system/components/primitives";
import type { AffectedRegion, EyeSide } from "@/lib/types";

export type ViewerLayer = "original" | "heatmap" | "overlay";

const LAYER_LABELS: Record<ViewerLayer, string> = {
  original: "Original",
  heatmap: "Heat map",
  overlay: "Overlay",
};

const ZOOM_MIN = 1;
const ZOOM_MAX = 6;
const ZOOM_STEP = 0.35;

export interface RetinalImageSource {
  eyeSide: EyeSide;
  originalUrl: string;
  heatmapUrl?: string | null;
  overlayUrl?: string | null;
  affectedRegions?: AffectedRegion[];
  capturedAt?: string;
}

interface Props {
  image: RetinalImageSource;
  /** When present, enables the side-by-side comparison control. */
  comparisonImage?: RetinalImageSource | null;
  showRegions?: boolean;
  className?: string;
}

export function RetinalImageViewer({
  image,
  comparisonImage,
  showRegions = false,
  className,
}: Props) {
  const [layer, setLayer] = useState<ViewerLayer>("original");
  const [zoom, setZoom] = useState(ZOOM_MIN);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [comparing, setComparing] = useState(false);
  const [regionsVisible, setRegionsVisible] = useState(showRegions);

  const dragState = useRef<{ x: number; y: number; active: boolean }>({
    x: 0,
    y: 0,
    active: false,
  });

  const hasExplanation = Boolean(image.heatmapUrl || image.overlayUrl);

  const resetView = useCallback(() => {
    setZoom(ZOOM_MIN);
    setOffset({ x: 0, y: 0 });
  }, []);

  // Reset the transform when the image changes, so a new case never inherits
  // the previous one's pan/zoom.
  useEffect(() => {
    resetView();
  }, [image.originalUrl, resetView]);

  const changeZoom = useCallback((delta: number) => {
    setZoom((current) => {
      const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, current + delta));
      if (next === ZOOM_MIN) setOffset({ x: 0, y: 0 });
      return next;
    });
  }, []);

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (zoom === ZOOM_MIN) return;
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

  // Keyboard parity for pan/zoom — a mouse must never be required.
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const nudge = 24;
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

  const sourceFor = (source: RetinalImageSource, activeLayer: ViewerLayer): string => {
    if (activeLayer === "heatmap" && source.heatmapUrl) return source.heatmapUrl;
    if (activeLayer === "overlay" && source.overlayUrl) return source.overlayUrl;
    return source.originalUrl;
  };

  return (
    <figure className={cx("flex flex-col gap-3", className)}>
      {/* ---- imaging stage ---- */}
      <div
        className="relative overflow-hidden rounded-[var(--rs-radius-lg)]"
        style={{
          // A deep, non-black ground: the standard for judging fundus imagery.
          background:
            "radial-gradient(circle at 50% 45%, #12181f 0%, #05080c 70%, #020406 100%)",
          border: "1px solid var(--rs-line)",
          boxShadow: "var(--rs-shadow-panel)",
        }}
      >
        <div
          role="group"
          aria-label={`Retinal image, ${image.eyeSide} eye. Use arrow keys to pan, plus and minus to zoom, zero to reset.`}
          tabIndex={0}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
          onKeyDown={onKeyDown}
          className="relative flex items-center justify-center outline-none"
          style={{
            aspectRatio: "4 / 3",
            cursor: zoom > ZOOM_MIN ? "grab" : "default",
            touchAction: "none",
          }}
        >
          <div className={cx("grid h-full w-full", comparing ? "grid-cols-2 gap-1" : "grid-cols-1")}>
            <ImageStage
              source={image}
              url={sourceFor(image, layer)}
              layer={layer}
              zoom={zoom}
              offset={offset}
              regions={regionsVisible ? image.affectedRegions : undefined}
            />
            {comparing && comparisonImage && (
              <ImageStage
                source={comparisonImage}
                url={sourceFor(comparisonImage, layer)}
                layer={layer}
                zoom={zoom}
                offset={offset}
                regions={regionsVisible ? comparisonImage.affectedRegions : undefined}
              />
            )}
          </div>

          {/* Eye designation — clinically essential, always visible. */}
          <span
            className="pointer-events-none absolute left-3 top-3 rounded-[var(--rs-radius-xs)] px-2 py-1 text-[var(--rs-text-2xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
            style={{ background: "rgba(0,0,0,0.55)", color: "#dce6f2" }}
          >
            {image.eyeSide === "left" ? "Left eye (OS)" : "Right eye (OD)"}
          </span>

          {zoom > ZOOM_MIN && (
            <span
              className="rs-numeric pointer-events-none absolute right-3 top-3 rounded-[var(--rs-radius-xs)] px-2 py-1 text-[var(--rs-text-2xs)]"
              style={{ background: "rgba(0,0,0,0.55)", color: "#dce6f2" }}
            >
              {zoom.toFixed(1)}×
            </span>
          )}
        </div>
      </div>

      {/* ---- instrument controls ---- */}
      <div className="flex flex-wrap items-center gap-2">
        <div
          role="group"
          aria-label="Image layer"
          className="inline-flex overflow-hidden rounded-[var(--rs-radius-md)] border"
          style={{ borderColor: "var(--rs-line)" }}
        >
          {(Object.keys(LAYER_LABELS) as ViewerLayer[]).map((option) => {
            const disabled = option !== "original" && !hasExplanation;
            const active = layer === option;
            return (
              <button
                key={option}
                type="button"
                disabled={disabled}
                aria-pressed={active}
                onClick={() => setLayer(option)}
                className="px-3 py-1.5 text-[var(--rs-text-xs)] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                style={{
                  background: active ? "var(--rs-accent)" : "var(--rs-surface-raised)",
                  color: active ? "var(--rs-accent-ink)" : "var(--rs-ink-muted)",
                }}
              >
                {LAYER_LABELS[option]}
              </button>
            );
          })}
        </div>

        <ViewerButton onClick={() => changeZoom(ZOOM_STEP)} label="Zoom in">
          +
        </ViewerButton>
        <ViewerButton onClick={() => changeZoom(-ZOOM_STEP)} label="Zoom out">
          −
        </ViewerButton>
        <ViewerButton onClick={resetView} label="Fit to view">
          Fit
        </ViewerButton>

        {image.affectedRegions && image.affectedRegions.length > 0 && (
          <ViewerButton
            onClick={() => setRegionsVisible((v) => !v)}
            label="Toggle attention regions"
            active={regionsVisible}
          >
            Regions
          </ViewerButton>
        )}

        {comparisonImage && (
          <ViewerButton
            onClick={() => setComparing((v) => !v)}
            label="Toggle side-by-side comparison"
            active={comparing}
          >
            Compare
          </ViewerButton>
        )}
      </div>

      {layer !== "original" && (
        <figcaption className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
          Grad-CAM indicates image regions that influenced the model's output. It is
          not a validated lesion detector and does not localise pathology.
        </figcaption>
      )}
    </figure>
  );
}

function ImageStage({
  source,
  url,
  layer,
  zoom,
  offset,
  regions,
}: {
  source: RetinalImageSource;
  url: string;
  layer: ViewerLayer;
  zoom: number;
  offset: { x: number; y: number };
  regions?: AffectedRegion[];
}) {
  return (
    <div className="relative h-full w-full overflow-hidden">
      <img
        src={url}
        alt={`Retinal photograph of the ${source.eyeSide} eye${
          layer === "original" ? "" : ` with ${LAYER_LABELS[layer].toLowerCase()} applied`
        }`}
        draggable={false}
        className="h-full w-full select-none object-contain"
        style={{
          transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
          transition: "transform var(--rs-duration) var(--rs-ease)",
        }}
      />
      {regions?.map((region) => (
        <div
          key={region.region}
          className="pointer-events-none absolute rounded-[var(--rs-radius-xs)]"
          style={{
            left: `${region.bounds.x * 100}%`,
            top: `${region.bounds.y * 100}%`,
            width: `${region.bounds.width * 100}%`,
            height: `${region.bounds.height * 100}%`,
            border: "1px dashed rgba(255,255,255,0.55)",
          }}
        >
          <span
            className="rs-numeric absolute left-1 top-1 rounded px-1 text-[10px]"
            style={{ background: "rgba(0,0,0,0.6)", color: "#e8eef5" }}
          >
            {region.region} · {(region.intensity * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
}

function ViewerButton({
  children,
  onClick,
  label,
  active,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      className="min-w-[2.5rem] rounded-[var(--rs-radius-md)] border px-3 py-1.5 text-[var(--rs-text-xs)] font-semibold transition-colors"
      style={{
        borderColor: "var(--rs-line)",
        background: active ? "var(--rs-accent)" : "var(--rs-surface-raised)",
        color: active ? "var(--rs-accent-ink)" : "var(--rs-ink-muted)",
      }}
    >
      {children}
    </button>
  );
}
