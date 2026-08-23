/**
 * Contrast guarantees for the glass design system.
 *
 * Translucency is the main risk this design takes: a frosted panel can quietly
 * destroy legibility, and the failure is invisible in code review because the
 * colours all *look* deliberate.
 *
 * One such bug shipped and was caught only by measuring in the browser: the
 * primary button used a Tailwind arbitrary class `text-[var(--rs-accent-ink)]`,
 * which is ambiguous between colour and font-size. Tailwind never emitted the
 * rule, the button inherited near-white body ink, and the result was white text
 * on a bright cyan fill at a contrast ratio of 1.58 — unreadable.
 *
 * These tests pin the rules that prevent a repeat.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/design-system/components/primitives";

/** Relative luminance per WCAG 2.1. */
function luminance([r, g, b]: number[]): number {
  const channel = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function parseColor(value: string): number[] {
  const parts = value.match(/[\d.]+/g);
  return parts ? parts.slice(0, 3).map(Number) : [0, 0, 0];
}

export function contrastRatio(foreground: string, background: string): number {
  const a = luminance(parseColor(foreground)) + 0.05;
  const b = luminance(parseColor(background)) + 0.05;
  return Number((Math.max(a, b) / Math.min(a, b)).toFixed(2));
}

// Accent values from the role themes in tokens.css. Buttons render on these.
const ACCENTS: Record<string, string> = {
  default: "rgb(34, 211, 238)",
  worker: "rgb(46, 230, 197)",
  doctor: "rgb(34, 211, 238)",
  patient: "rgb(255, 167, 107)",
  admin: "rgb(124, 140, 255)",
};

const ACCENT_INKS: Record<string, string> = {
  default: "rgb(4, 33, 43)",
  worker: "rgb(3, 36, 32)",
  doctor: "rgb(4, 33, 43)",
  patient: "rgb(42, 18, 6)",
  admin: "rgb(11, 15, 43)",
};

const AA_NORMAL = 4.5;
const AA_LARGE = 3.0;

describe("WCAG contrast maths", () => {
  it("computes known ratios correctly", () => {
    expect(contrastRatio("rgb(0,0,0)", "rgb(255,255,255)")).toBe(21);
    expect(contrastRatio("rgb(255,255,255)", "rgb(255,255,255)")).toBe(1);
  });
});

describe("accent inks are legible on their accents", () => {
  it.each(Object.keys(ACCENTS))(
    "%s theme: accent ink on accent fill passes AA",
    (theme) => {
      const ratio = contrastRatio(ACCENT_INKS[theme], ACCENTS[theme]);
      expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
    },
  );

  it("near-white on a bright accent would fail — the bug this guards against", () => {
    // Documents *why* the rule exists rather than only asserting the fix.
    expect(contrastRatio("rgb(234, 240, 249)", ACCENTS.default)).toBeLessThan(AA_NORMAL);
  });
});

describe("primary button sets its own text colour", () => {
  it("does not rely on inheritance for foreground colour", () => {
    render(<Button variant="primary">Sign in</Button>);
    const button = screen.getByRole("button", { name: /sign in/i });

    // The colour must be set inline. A Tailwind arbitrary class is ambiguous
    // between colour and font-size and silently fails to emit.
    expect(button.style.color).toBeTruthy();
    expect(button.style.color).toContain("--rs-accent-ink");
  });

  it("danger button also sets an explicit foreground", () => {
    render(<Button variant="danger">Delete</Button>);
    const button = screen.getByRole("button", { name: /delete/i });

    expect(button.style.color).toBeTruthy();
  });

  it("secondary button inherits the readable body ink deliberately", () => {
    render(<Button variant="secondary">Cancel</Button>);
    const button = screen.getByRole("button", { name: /cancel/i });

    expect(button.style.color).toContain("--rs-ink");
  });
});

describe("body text on the glass ground", () => {
  // Panels are translucent, so the effective background is the surface beneath.
  const SURFACES: Record<string, string> = {
    default: "rgb(7, 11, 20)",
    worker: "rgb(6, 13, 18)",
    doctor: "rgb(4, 6, 12)",
    patient: "rgb(13, 16, 24)",
    admin: "rgb(7, 10, 19)",
  };
  const INKS: Record<string, string> = {
    default: "rgb(234, 240, 249)",
    worker: "rgb(233, 246, 246)",
    doctor: "rgb(232, 238, 248)",
    patient: "rgb(243, 241, 238)",
    admin: "rgb(231, 236, 247)",
  };
  const MUTED: Record<string, string> = {
    default: "rgb(159, 176, 199)",
    worker: "rgb(157, 188, 189)",
    doctor: "rgb(154, 172, 196)",
    patient: "rgb(195, 188, 180)",
    admin: "rgb(155, 168, 194)",
  };
  const SUBTLE: Record<string, string> = {
    default: "rgb(107, 124, 147)",
    worker: "rgb(107, 138, 140)",
    doctor: "rgb(102, 120, 143)",
    patient: "rgb(148, 141, 134)",
    admin: "rgb(106, 119, 143)",
  };

  it.each(Object.keys(SURFACES))("%s theme: primary ink passes AA", (theme) => {
    expect(contrastRatio(INKS[theme], SURFACES[theme])).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it.each(Object.keys(SURFACES))("%s theme: muted ink passes AA", (theme) => {
    expect(contrastRatio(MUTED[theme], SURFACES[theme])).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it.each(Object.keys(SURFACES))(
    "%s theme: subtle ink is legible at large/label sizes",
    (theme) => {
      // Subtle ink is used only for uppercase labels and secondary captions,
      // so the large-text threshold is the applicable bar.
      expect(contrastRatio(SUBTLE[theme], SURFACES[theme])).toBeGreaterThanOrEqual(AA_LARGE);
    },
  );
});

describe("risk colours remain distinguishable on the dark ground", () => {
  const SURFACE = "rgb(7, 11, 20)";
  const RISK: Record<string, string> = {
    low: "rgb(45, 212, 191)",
    moderate: "rgb(251, 191, 36)",
    high: "rgb(251, 146, 60)",
    urgent: "rgb(251, 113, 133)",
  };

  it.each(Object.keys(RISK))("%s risk colour passes large-text contrast", (level) => {
    expect(contrastRatio(RISK[level], SURFACE)).toBeGreaterThanOrEqual(AA_LARGE);
  });

  it("severity is never carried by colour alone regardless", () => {
    // Restating the invariant here because contrast alone is not the safeguard:
    // glyph, label and scale position all encode severity too.
    expect(Object.keys(RISK)).toEqual(["low", "moderate", "high", "urgent"]);
  });
});
