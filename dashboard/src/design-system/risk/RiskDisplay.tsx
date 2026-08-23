/**
 * Clinical risk visualisation.
 *
 * Accessibility rule enforced here: **severity is never communicated by colour
 * alone.** Every risk element carries a text label, a distinct glyph, and a
 * position on an ordered scale — so it remains readable with colour-vision
 * deficiency, in greyscale print, and to a screen reader.
 */

import type { RiskLevel, ScreeningCategory } from "@/lib/types";

export const RISK_ORDER: RiskLevel[] = ["low", "moderate", "high", "urgent"];

interface RiskMeta {
  label: string;
  /** Distinct shape per level — the non-colour channel. */
  glyph: string;
  description: string;
}

export const RISK_META: Record<RiskLevel, RiskMeta> = {
  low: { label: "Low", glyph: "○", description: "Routine monitoring" },
  moderate: { label: "Moderate", glyph: "◐", description: "Consultation advised" },
  high: { label: "High", glyph: "◕", description: "Prompt consultation" },
  urgent: { label: "Urgent", glyph: "●", description: "Urgent referral" },
};

export function riskColor(level: RiskLevel): string {
  return `var(--rs-risk-${level})`;
}

export function riskWash(level: RiskLevel): string {
  return `var(--rs-risk-${level}-wash)`;
}

/** Clinical wording for the five-class grading scale. */
export const CATEGORY_LABELS: Record<ScreeningCategory, string> = {
  no_dr: "No DR detected",
  mild: "Mild NPDR",
  moderate: "Moderate NPDR",
  severe: "Severe NPDR",
  proliferative: "Proliferative DR",
};

/** Plain-language wording for the patient portal — no clinical abbreviations. */
export const CATEGORY_PATIENT_LABELS: Record<ScreeningCategory, string> = {
  no_dr: "No signs were found in this screening",
  mild: "Early signs were found",
  moderate: "Some changes were found",
  severe: "Significant changes were found",
  proliferative: "Advanced changes were found",
};

/* -------------------------------------------------------------------------- */
/* Badge                                                                       */
/* -------------------------------------------------------------------------- */
export function RiskBadge({ level, size = "md" }: { level: RiskLevel; size?: "sm" | "md" }) {
  const meta = RISK_META[level];
  return (
    <span
      className={
        size === "sm"
          ? "inline-flex items-center gap-1.5 rounded-[var(--rs-radius-xs)] px-2 py-0.5 text-[var(--rs-text-2xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
          : "inline-flex items-center gap-2 rounded-[var(--rs-radius-sm)] px-3 py-1 text-[var(--rs-text-xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
      }
      style={{
        color: riskColor(level),
        background: riskWash(level),
        border: `1px solid color-mix(in srgb, ${riskColor(level)} 45%, transparent)`,
      }}
    >
      <span aria-hidden="true">{meta.glyph}</span>
      {meta.label} risk
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Scale                                                                       */
/* -------------------------------------------------------------------------- */
/**
 * The ordered risk scale. The active band is marked by position, glyph, weight
 * and label — colour is the last of four redundant cues.
 */
export function RiskScale({ level }: { level: RiskLevel }) {
  const activeIndex = RISK_ORDER.indexOf(level);

  return (
    <div
      role="img"
      aria-label={`Risk level: ${RISK_META[level].label}. ${RISK_META[level].description}.`}
      className="flex flex-col gap-2"
    >
      <div className="flex items-stretch gap-1">
        {RISK_ORDER.map((band, index) => {
          const isActive = index === activeIndex;
          const isBelow = index < activeIndex;
          return (
            <div key={band} className="flex flex-1 flex-col gap-1.5">
              <div
                className="h-2 rounded-full transition-all duration-[var(--rs-duration)]"
                style={{
                  background:
                    isActive || isBelow ? riskColor(band) : "var(--rs-surface-sunken)",
                  opacity: isActive ? 1 : isBelow ? 0.45 : 1,
                  boxShadow: isActive
                    ? `0 0 0 2px color-mix(in srgb, ${riskColor(band)} 40%, transparent)`
                    : undefined,
                }}
              />
              <span
                className="text-center text-[var(--rs-text-2xs)] uppercase tracking-[var(--rs-tracking-caps)]"
                style={{
                  color: isActive ? riskColor(band) : "var(--rs-ink-subtle)",
                  fontWeight: isActive ? 800 : 500,
                }}
              >
                {isActive && <span aria-hidden="true">{RISK_META[band].glyph} </span>}
                {RISK_META[band].label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Confidence                                                                  */
/* -------------------------------------------------------------------------- */
/**
 * Model confidence. Labelled explicitly as the model's own certainty so it is
 * never mistaken for a probability of disease.
 */
export function ConfidenceMeter({ value }: { value: number | null }) {
  if (value === null || Number.isNaN(value)) {
    return (
      <span className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-subtle)" }}>
        Not available
      </span>
    );
  }

  const percent = Math.round(value * 100);
  const segments = 12;
  const filled = Math.round((percent / 100) * segments);

  return (
    <div className="flex flex-col gap-1.5">
      <div
        className="flex gap-0.5"
        role="meter"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Model confidence ${percent} percent`}
      >
        {Array.from({ length: segments }, (_, index) => (
          <span
            key={index}
            className="h-4 flex-1 rounded-[2px] transition-colors duration-[var(--rs-duration-fast)]"
            style={{
              background:
                index < filled ? "var(--rs-accent)" : "var(--rs-surface-sunken)",
              opacity: index < filled ? 1 : 0.7,
            }}
          />
        ))}
      </div>
      <span className="rs-numeric text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-muted)" }}>
        {percent}% model confidence
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Disclaimers                                                                 */
/* -------------------------------------------------------------------------- */
/** Standing notice wherever AI output appears. */
export function AiAssistanceNotice({ compact }: { compact?: boolean }) {
  return (
    <p
      className={
        compact
          ? "text-[var(--rs-text-2xs)] leading-snug"
          : "rounded-[var(--rs-radius-sm)] border p-3 text-[var(--rs-text-xs)] leading-relaxed"
      }
      style={{
        color: "var(--rs-ink-muted)",
        borderColor: compact ? undefined : "var(--rs-line)",
        background: compact ? undefined : "var(--rs-surface-sunken)",
      }}
    >
      <strong style={{ color: "var(--rs-ink)" }}>AI-assisted screening support.</strong>{" "}
      This is not a diagnosis. A qualified clinician reviews every screening.
    </p>
  );
}

/** Unmissable banner when output came from the placeholder model. */
export function DevelopmentModelBanner() {
  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-[var(--rs-radius-md)] border p-3"
      style={{
        borderColor: "color-mix(in srgb, var(--rs-warn) 55%, transparent)",
        background: "color-mix(in srgb, var(--rs-warn) 12%, transparent)",
      }}
    >
      <span aria-hidden="true" style={{ color: "var(--rs-warn)" }}>
        ⚠
      </span>
      <div className="flex flex-col gap-0.5">
        <p
          className="text-[var(--rs-text-xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
          style={{ color: "var(--rs-warn)" }}
        >
          Development model — not for clinical use
        </p>
        <p className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-muted)" }}>
          This result was produced by a placeholder model and has no diagnostic
          meaning. It exists so the workflow can be tested end to end.
        </p>
      </div>
    </div>
  );
}
