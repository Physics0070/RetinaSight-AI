/** Workflow-state chip. Label + glyph, so state never depends on colour alone. */

const STATE_META: Record<string, { label: string; glyph: string; tone: string }> = {
  idle: { label: "Not started", glyph: "○", tone: "var(--rs-ink-subtle)" },
  patient_selected: { label: "Patient selected", glyph: "◔", tone: "var(--rs-info)" },
  capture_left_eye: { label: "Capturing left eye", glyph: "◑", tone: "var(--rs-info)" },
  capture_right_eye: { label: "Capturing right eye", glyph: "◑", tone: "var(--rs-info)" },
  quality_check: { label: "Checking quality", glyph: "◎", tone: "var(--rs-info)" },
  retake_required: { label: "Retake required", glyph: "↻", tone: "var(--rs-warn)" },
  ready_for_inference: { label: "Ready to screen", glyph: "▶", tone: "var(--rs-accent)" },
  inference_running: { label: "Screening", glyph: "◌", tone: "var(--rs-accent)" },
  result_available: { label: "Result ready", glyph: "◕", tone: "var(--rs-ok)" },
  explanation_available: { label: "Explanation ready", glyph: "◕", tone: "var(--rs-ok)" },
  referral_pending: { label: "Referral pending", glyph: "➜", tone: "var(--rs-warn)" },
  referral_created: { label: "Referral created", glyph: "➜", tone: "var(--rs-ok)" },
  doctor_review: { label: "Awaiting review", glyph: "⚕", tone: "var(--rs-info)" },
  follow_up: { label: "Follow-up set", glyph: "↻", tone: "var(--rs-ok)" },
  completed: { label: "Completed", glyph: "●", tone: "var(--rs-ok)" },
  cancelled: { label: "Cancelled", glyph: "✕", tone: "var(--rs-ink-subtle)" },
  sync_pending: { label: "Waiting to sync", glyph: "⇅", tone: "var(--rs-warn)" },
  synced: { label: "Synced", glyph: "✓", tone: "var(--rs-ok)" },
  error: { label: "Needs attention", glyph: "!", tone: "var(--rs-danger)" },
};

export function ScreeningStateChip({ state }: { state: string }) {
  const meta = STATE_META[state] ?? {
    label: state.replace(/_/g, " "),
    glyph: "○",
    tone: "var(--rs-ink-subtle)",
  };

  return (
    <span
      className="inline-flex w-fit items-center gap-1.5 rounded-[var(--rs-radius-xs)] px-2 py-0.5 text-[var(--rs-text-2xs)] font-bold uppercase tracking-[var(--rs-tracking-caps)]"
      style={{
        color: meta.tone,
        background: `color-mix(in srgb, ${meta.tone} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${meta.tone} 35%, transparent)`,
      }}
    >
      <span aria-hidden="true">{meta.glyph}</span>
      {meta.label}
    </span>
  );
}

export function stateLabel(state: string): string {
  return STATE_META[state]?.label ?? state.replace(/_/g, " ");
}
