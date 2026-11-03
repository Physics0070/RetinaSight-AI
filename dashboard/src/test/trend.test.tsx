/** Patient trend/compare, printable report and landing page. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
vi.mock("@/lib/api", () => ({ api: { get: (...a: unknown[]) => get(...a) } }));
vi.mock("@/app/EyeScene", () => ({ default: () => <div data-testid="eye" /> }));

import { Landing } from "@/app/Landing";
import { PatientTrend } from "@/portals/doctor/PatientTrend";
import { ScreeningReport } from "@/portals/doctor/ScreeningReport";
import { trendOf } from "@/lib/trend";

const detail = (id: string, day: string, category: string, risk = "low") => ({
  id,
  state: "completed",
  created_at: `2026-0${day}-01T00:00:00Z`,
  completed_at: `2026-0${day}-01T00:00:00Z`,
  patient: { full_name: "Aarti Deshmukh", patient_code: "DEMO-0001" },
  results: [{ eye_side: "left", category, confidence: 0.9, model_version: "dr-v2" }],
  risk: { risk_level: risk, recommended_action: "See an eye specialist.", reason: "r" },
});

describe("trendOf", () => {
  it("reads grade movement between the two latest graded visits", () => {
    expect(trendOf([0, 1, 3])).toBe("worsening");
    expect(trendOf([3, 2])).toBe("improving");
    expect(trendOf([2, 2])).toBe("stable");
    expect(trendOf([2])).toBe("insufficient");
    expect(trendOf([null, 2])).toBe("insufficient");
  });
});

describe("PatientTrend", () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation((path: string) => {
      if (path === "/screenings")
        return Promise.resolve({ items: [{ id: "s2" }, { id: "s1" }], total: 2 });
      if (path === "/screenings/s1") return Promise.resolve(detail("s1", "1", "mild"));
      if (path === "/screenings/s2") return Promise.resolve(detail("s2", "2", "severe", "urgent"));
      return Promise.reject(new Error(path));
    });
  });

  it("shows direction and compares the two latest visits", async () => {
    render(<MemoryRouter><PatientTrend patientId="p1" /></MemoryRouter>);
    expect(await screen.findByText(/worsening/i)).toBeInTheDocument();
    expect(screen.getAllByText("Mild NPDR").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Severe NPDR").length).toBeGreaterThan(0);
  });
});

describe("ScreeningReport", () => {
  it("prints, and always carries the not-a-diagnosis notice", async () => {
    get.mockResolvedValue(detail("s2", "2", "severe", "urgent"));
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    render(
      <MemoryRouter initialEntries={["/doctor/reports/s2"]}>
        <Routes><Route path="/doctor/reports/:sessionId" element={<ScreeningReport />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Severe NPDR")).toBeInTheDocument();
    expect(screen.getByText(/not a diagnosis/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save as pdf/i }));
    await waitFor(() => expect(print).toHaveBeenCalled());
  });
});

describe("Landing", () => {
  it("offers sign-in and renders the 3D eye", async () => {
    render(<MemoryRouter><Landing /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
    expect(await screen.findByTestId("eye")).toBeInTheDocument();
  });
});
