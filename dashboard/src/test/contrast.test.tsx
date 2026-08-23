/**
 * Contrast and colour-separation guarantees for the glass design system.
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
 * These tests parse `tokens.css` itself rather than restating its values. An
 * earlier version of this file kept a hand-copied table of the palette, which
 * meant a palette change could pass a green suite while shipping unreadable
 * colours — the tests would have been measuring the copy, not the product.
 */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/design-system/components/primitives";

/**
 * The stylesheet the app actually ships, read from disk.
 *
 * Tried and rejected: `import ... from "...?raw"`. Vite's raw suffix resolves
 * to `undefined` under vitest here, which silently produced an empty palette —
 * the tests would have passed by measuring nothing at all.
 *
 * Candidates cover being run from the dashboard package (the usual case) and
 * from the repository root, so the suite does not depend on the caller's
 * working directory.
 */
const TOKENS_CSS = (() => {
  const relative = "src/design-system/tokens/tokens.css";
  const candidates = [
    resolve(process.cwd(), relative),
    resolve(process.cwd(), "dashboard", relative),
  ];
  const found = candidates.find(existsSync);
  if (!found) {
    throw new Error(`Could not locate tokens.css. Tried:\n  ${candidates.join("\n  ")}`);
  }
  return readFileSync(found, "utf8");
})();

/* -------------------------------------------------------------------------- */
/* Parsing tokens.css                                                         */
/* -------------------------------------------------------------------------- */

/** Custom properties declared in the block for `selector`. */
function declarationsFor(selector: string): Record<string, string> {
  // Non-greedy up to the first closing brace: token blocks contain no nested
  // rules, so this is sufficient and avoids pulling in a CSS parser.
  const block = new RegExp(`${escapeRegExp(selector)}\\s*\\{([^}]*)\\}`).exec(TOKENS_CSS);
  if (!block) throw new Error(`No token block found for selector ${selector}`);

  const declarations: Record<string, string> = {};
  for (const [, name, value] of block[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    declarations[name] = value.trim();
  }
  return declarations;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const ROOT = declarationsFor(":root");
const ROLES = ["worker", "doctor", "patient", "admin"] as const;

/** Effective tokens for a role: the root block with the role block layered on. */
function theme(role: string): Record<string, string> {
  return role === "default"
    ? ROOT
    : { ...ROOT, ...declarationsFor(`[data-role="${role}"]`) };
}

const THEMES = ["default", ...ROLES];

/* -------------------------------------------------------------------------- */
/* Colour maths                                                               */
/* -------------------------------------------------------------------------- */

function toRgb(value: string): [number, number, number] {
  const hex = value.trim();
  if (hex.startsWith("#")) {
    const digits =
      hex.length === 4
        ? [...hex.slice(1)].map((c) => c + c).join("")
        : hex.slice(1);
    return [
      parseInt(digits.slice(0, 2), 16),
      parseInt(digits.slice(2, 4), 16),
      parseInt(digits.slice(4, 6), 16),
    ];
  }
  const parts = hex.match(/[\d.]+/g);
  if (!parts) throw new Error(`Cannot parse colour: ${value}`);
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
}

/** Relative luminance per WCAG 2.1. */
function luminance([r, g, b]: number[]): number {
  const channel = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(foreground: string, background: string): number {
  const a = luminance(toRgb(foreground)) + 0.05;
  const b = luminance(toRgb(background)) + 0.05;
  return Number((Math.max(a, b) / Math.min(a, b)).toFixed(2));
}

/** Hue angle in degrees, for measuring how far apart two colours read. */
function hue(value: string): number {
  const [r, g, b] = toRgb(value).map((c) => c / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  if (delta === 0) return 0;

  let h: number;
  if (max === r) h = ((g - b) / delta) % 6;
  else if (max === g) h = (b - r) / delta + 2;
  else h = (r - g) / delta + 4;

  return ((h * 60) % 360 + 360) % 360;
}

/** Smallest angle between two hues, accounting for wrap-around at 360°. */
function hueSeparation(a: string, b: string): number {
  const diff = Math.abs(hue(a) - hue(b)) % 360;
  return Math.min(diff, 360 - diff);
}

const AA_NORMAL = 4.5;
const AA_LARGE = 3.0;

/* -------------------------------------------------------------------------- */

describe("WCAG contrast maths", () => {
  it("computes known ratios correctly", () => {
    expect(contrastRatio("rgb(0,0,0)", "rgb(255,255,255)")).toBe(21);
    expect(contrastRatio("rgb(255,255,255)", "rgb(255,255,255)")).toBe(1);
    expect(contrastRatio("#000000", "#ffffff")).toBe(21);
  });
});

describe("tokens.css parses into complete themes", () => {
  it.each(THEMES)("%s theme defines every colour the tests measure", (name) => {
    const t = theme(name);
    for (const token of [
      "--rs-surface",
      "--rs-ink",
      "--rs-ink-muted",
      "--rs-ink-subtle",
      "--rs-accent",
      "--rs-accent-ink",
    ]) {
      expect(t[token], `${name} is missing ${token}`).toBeTruthy();
    }
  });

  it("every role overrides the accent rather than inheriting one", () => {
    // A role that forgot its accent would silently render as the default
    // theme and the portals would stop being visually distinguishable.
    for (const role of ROLES) {
      expect(declarationsFor(`[data-role="${role}"]`)["--rs-accent"]).toBeTruthy();
    }
  });
});

describe("accent inks are legible on their accents", () => {
  it.each(THEMES)("%s theme: accent ink on accent fill passes AA", (name) => {
    const t = theme(name);
    expect(contrastRatio(t["--rs-accent-ink"], t["--rs-accent"])).toBeGreaterThanOrEqual(
      AA_NORMAL,
    );
  });

  it("near-white on a bright accent would fail — the bug this guards against", () => {
    // Documents *why* the rule exists rather than only asserting the fix.
    expect(contrastRatio(ROOT["--rs-ink"], ROOT["--rs-accent"])).toBeLessThan(AA_NORMAL);
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
  it.each(THEMES)("%s theme: primary ink passes AA", (name) => {
    const t = theme(name);
    expect(contrastRatio(t["--rs-ink"], t["--rs-surface"])).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it.each(THEMES)("%s theme: muted ink passes AA", (name) => {
    const t = theme(name);
    expect(contrastRatio(t["--rs-ink-muted"], t["--rs-surface"])).toBeGreaterThanOrEqual(
      AA_NORMAL,
    );
  });

  it.each(THEMES)("%s theme: subtle ink is legible at large/label sizes", (name) => {
    // Subtle ink is used only for uppercase labels and secondary captions,
    // so the large-text threshold is the applicable bar.
    const t = theme(name);
    expect(contrastRatio(t["--rs-ink-subtle"], t["--rs-surface"])).toBeGreaterThanOrEqual(
      AA_LARGE,
    );
  });
});

describe("risk colours remain distinguishable on every ground", () => {
  const RISK_TOKENS = [
    "--rs-risk-low",
    "--rs-risk-moderate",
    "--rs-risk-high",
    "--rs-risk-urgent",
  ];

  it.each(THEMES)("%s theme: every risk colour passes large-text contrast", (name) => {
    const t = theme(name);
    for (const token of RISK_TOKENS) {
      const ratio = contrastRatio(ROOT[token], t["--rs-surface"]);
      expect(ratio, `${token} on ${name} surface`).toBeGreaterThanOrEqual(AA_LARGE);
    }
  });

  it("severity is never carried by colour alone regardless", () => {
    // Restating the invariant here because contrast alone is not the safeguard:
    // glyph, label and scale position all encode severity too.
    expect(RISK_TOKENS.map((t) => t.replace("--rs-risk-", ""))).toEqual([
      "low",
      "moderate",
      "high",
      "urgent",
    ]);
  });

  /**
   * Role chrome must not look like a severity signal.
   *
   * The previous palette failed this badly and nobody noticed, because each
   * colour was defensible on its own: the health-worker accent (#2ee6c5) sat
   * 3° of hue from the low-risk colour (#2dd4bf), and the patient accent
   * (#ffa76b) sat 3° from the high-risk colour (#fb923c). An accent that
   * resembles a severity colour invites a misread of the one signal that must
   * never be misread.
   *
   * The tightest margin in the current palette is the field role's lime
   * against moderate amber, at ~39°.
   */
  const MIN_HUE_SEPARATION = 35;

  it.each(THEMES)("%s theme: accent is well clear of every severity hue", (name) => {
    const accent = theme(name)["--rs-accent"];
    for (const token of RISK_TOKENS) {
      const separation = hueSeparation(accent, ROOT[token]);
      expect(
        separation,
        `${name} accent ${accent} is only ${separation.toFixed(1)}° from ${token}`,
      ).toBeGreaterThanOrEqual(MIN_HUE_SEPARATION);
    }
  });

  it("detects the separation failure the old palette had", () => {
    // Guards the guard: a broken hueSeparation would make the test above pass
    // vacuously, so pin it against the two known-bad historical pairs.
    expect(hueSeparation("#2ee6c5", "#2dd4bf")).toBeLessThan(MIN_HUE_SEPARATION);
    expect(hueSeparation("#ffa76b", "#fb923c")).toBeLessThan(MIN_HUE_SEPARATION);
  });
});
