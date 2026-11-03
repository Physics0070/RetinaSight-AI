import type { InferenceResult, ScreeningCategory, ScreeningSessionDetail } from "./types";

export const GRADE: Record<ScreeningCategory, number> = {
  no_dr: 0,
  mild: 1,
  moderate: 2,
  severe: 3,
  proliferative: 4,
};

/** The worse eye drives the visit: a clinician acts on the worst finding. */
export function worstResult(results: InferenceResult[]): InferenceResult | null {
  let worst: InferenceResult | null = null;
  for (const r of results) {
    if (r.category && (!worst || GRADE[r.category] > GRADE[worst.category!])) worst = r;
  }
  return worst;
}

export type Trend = "worsening" | "improving" | "stable" | "insufficient";

/** Grades are oldest-first; compares the last two. */
export function trendOf(grades: (number | null)[]): Trend {
  const [prev, last] = grades.slice(-2);
  if (grades.length < 2 || prev == null || last == null) return "insufficient";
  return last > prev ? "worsening" : last < prev ? "improving" : "stable";
}

export const visitGrade = (s: ScreeningSessionDetail) => {
  const w = worstResult(s.results);
  return w?.category ? GRADE[w.category] : null;
};
