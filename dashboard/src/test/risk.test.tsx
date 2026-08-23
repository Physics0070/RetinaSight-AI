/**
 * Risk display: the accessibility guarantee that severity is never carried by
 * colour alone, plus correct patient-facing language.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  AiAssistanceNotice,
  CATEGORY_LABELS,
  CATEGORY_PATIENT_LABELS,
  ConfidenceMeter,
  DevelopmentModelBanner,
  RISK_META,
  RISK_ORDER,
  RiskBadge,
  RiskScale,
} from "@/design-system/risk/RiskDisplay";

describe("risk severity is never colour-only", () => {
  it.each(RISK_ORDER)("badge for %s carries a text label", (level) => {
    render(<RiskBadge level={level} />);
    expect(screen.getByText(new RegExp(RISK_META[level].label, "i"))).toBeInTheDocument();
  });

  it.each(RISK_ORDER)("badge for %s carries a distinct glyph", (level) => {
    const { container } = render(<RiskBadge level={level} />);
    expect(container.textContent).toContain(RISK_META[level].glyph);
  });

  it("uses a different glyph for every level", () => {
    const glyphs = RISK_ORDER.map((level) => RISK_META[level].glyph);
    expect(new Set(glyphs).size).toBe(RISK_ORDER.length);
  });

  it("exposes the scale to assistive technology with a described level", () => {
    render(<RiskScale level="urgent" />);
    const scale = screen.getByRole("img");
    expect(scale).toHaveAccessibleName(/urgent/i);
    expect(scale).toHaveAccessibleName(/urgent referral/i);
  });

  it("orders the scale from low to urgent", () => {
    expect(RISK_ORDER).toEqual(["low", "moderate", "high", "urgent"]);
  });
});

describe("confidence meter", () => {
  it("reports the model's own confidence, labelled as such", () => {
    render(<ConfidenceMeter value={0.82} />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "82");
    expect(screen.getByText(/82% model confidence/i)).toBeInTheDocument();
  });

  it("says 'not available' rather than showing a misleading zero", () => {
    render(<ConfidenceMeter value={null} />);
    expect(screen.getByText(/not available/i)).toBeInTheDocument();
    expect(screen.queryByRole("meter")).not.toBeInTheDocument();
  });
});

describe("clinical framing", () => {
  it("always states that AI output is not a diagnosis", () => {
    render(<AiAssistanceNotice />);
    expect(screen.getByText(/not a diagnosis/i)).toBeInTheDocument();
    expect(screen.getByText(/clinician/i)).toBeInTheDocument();
  });

  it("makes the development-model warning unmissable", () => {
    render(<DevelopmentModelBanner />);
    expect(screen.getByText(/not for clinical use/i)).toBeInTheDocument();
    expect(screen.getByText(/no diagnostic meaning/i)).toBeInTheDocument();
  });

  it("covers all five grading categories in both registers", () => {
    const categories = ["no_dr", "mild", "moderate", "severe", "proliferative"] as const;
    for (const category of categories) {
      expect(CATEGORY_LABELS[category]).toBeTruthy();
      expect(CATEGORY_PATIENT_LABELS[category]).toBeTruthy();
    }
  });

  it("keeps clinical abbreviations out of patient-facing wording", () => {
    for (const text of Object.values(CATEGORY_PATIENT_LABELS)) {
      expect(text).not.toMatch(/NPDR|\bDR\b|proliferative/i);
    }
  });
});
