/**
 * Doctor's clinical record UI: medical history and prescribing.
 *
 * The API is mocked at the module boundary so these assert the *screen's*
 * behaviour — what a clinician sees and can do — rather than re-testing the
 * endpoints, which have their own backend suite.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const post = vi.fn();
const patch = vi.fn();
const del = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    patch: (...args: unknown[]) => patch(...args),
    del: (...args: unknown[]) => del(...args),
  },
}));

import { PatientRecord } from "@/portals/doctor/PatientRecord";
import { Prescribe } from "@/portals/doctor/Prescribe";

const PATIENT = {
  id: "p1",
  patient_code: "DEMO-0001",
  full_name: "Aarti Deshmukh",
  date_of_birth: "1970-02-11",
  sex: "female",
  phone: null,
  has_diabetes: true,
  diabetes_duration_years: 12,
  clinic_id: null,
  created_at: new Date().toISOString(),
};

const ENTRY = {
  id: "h1",
  patient_id: "p1",
  entry_type: "allergy" as const,
  title: "Penicillin",
  detail: "Rash on exposure.",
  occurred_on: "2018-03-04",
  status: "ongoing",
  recorded_by_user_id: null,
  updated_by_user_id: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function routeFor(element: React.ReactNode, path = "/doctor/patients/p1") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/doctor/patients/:patientId" element={element} />
        <Route path="/doctor/patients/:patientId/prescribe" element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  patch.mockReset();
  del.mockReset();
});

function mockRecord(history: unknown[] = [ENTRY], prescriptions: unknown[] = []) {
  get.mockImplementation((path: string) => {
    if (path.endsWith("/history")) return Promise.resolve(history);
    if (path.endsWith("/prescriptions")) return Promise.resolve(prescriptions);
    return Promise.resolve(PATIENT);
  });
}

describe("patient medical history", () => {
  it("shows the patient's recorded history", async () => {
    mockRecord();
    routeFor(<PatientRecord />);

    expect(await screen.findByText("Penicillin")).toBeInTheDocument();
    expect(screen.getByText(/rash on exposure/i)).toBeInTheDocument();
    expect(screen.getByText(/occurred 2018-03-04/i)).toBeInTheDocument();
  });

  it("flags an allergy distinctly rather than burying it in a note", async () => {
    mockRecord();
    routeFor(<PatientRecord />);

    // The type is surfaced as its own badge — an allergy must not be skimmed past.
    expect(await screen.findByText("Allergy")).toBeInTheDocument();
  });

  it("lets the doctor add a new entry", async () => {
    mockRecord([]);
    post.mockResolvedValue({ ...ENTRY, id: "h2" });
    routeFor(<PatientRecord />);

    await userEvent.click(await screen.findByRole("button", { name: /add the first entry/i }));
    await userEvent.type(screen.getByLabelText(/title/i), "Type 2 diabetes mellitus");
    await userEvent.click(screen.getByRole("button", { name: /save entry/i }));

    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    const [path, body] = post.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe("/patients/p1/history");
    expect(body.title).toBe("Type 2 diabetes mellitus");
  });

  it("lets the doctor correct an existing entry", async () => {
    mockRecord();
    patch.mockResolvedValue({ ...ENTRY, status: "resolved" });
    routeFor(<PatientRecord />);

    await userEvent.click(await screen.findByRole("button", { name: /^edit$/i }));
    const status = screen.getByLabelText(/status/i);
    await userEvent.clear(status);
    await userEvent.type(status, "resolved");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(patch).toHaveBeenCalledOnce());
    const [path, body] = patch.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe("/history/h1");
    expect(body.status).toBe("resolved");
    // A correction must not blank the fields it did not touch.
    expect(body.title).toBe("Penicillin");
  });

  it("says plainly that removing retires an entry rather than deleting it", async () => {
    mockRecord();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    routeFor(<PatientRecord />);

    await userEvent.click(await screen.findByRole("button", { name: /^remove$/i }));

    expect(confirmSpy.mock.calls[0][0]).toMatch(/hidden, not deleted/i);
    // Declining the confirm must not call the API.
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

describe("prescribing", () => {
  it("will not issue a prescription until a medicine is fully specified", async () => {
    get.mockResolvedValue(PATIENT);
    routeFor(<Prescribe />, "/doctor/patients/p1/prescribe");

    const issue = await screen.findByRole("button", { name: /issue prescription/i });
    expect(issue).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/^medicine/i), "Metformin");
    expect(issue).toBeDisabled(); // name alone is not a prescription

    await userEvent.type(screen.getByLabelText(/^dose/i), "500 mg");
    await userEvent.type(screen.getByLabelText(/^frequency/i), "Twice daily");
    expect(issue).toBeEnabled();
  });

  it("sends the composed prescription to the API", async () => {
    get.mockResolvedValue(PATIENT);
    post.mockResolvedValue({ id: "rx1" });
    routeFor(<Prescribe />, "/doctor/patients/p1/prescribe");

    await userEvent.type(await screen.findByLabelText(/^medicine/i), "Metformin");
    await userEvent.type(screen.getByLabelText(/^dose/i), "500 mg");
    await userEvent.type(screen.getByLabelText(/^frequency/i), "Twice daily");
    await userEvent.type(screen.getByLabelText(/diagnosis/i), "Moderate NPDR");
    await userEvent.click(screen.getByRole("button", { name: /issue prescription/i }));

    await waitFor(() => expect(post).toHaveBeenCalledOnce());
    const [path, body] = post.mock.calls[0] as [string, { items: unknown[]; diagnosis: string }];
    expect(path).toBe("/patients/p1/prescriptions");
    expect(body.diagnosis).toBe("Moderate NPDR");
    expect(body.items).toEqual([
      {
        name: "Metformin",
        dose: "500 mg",
        frequency: "Twice daily",
        duration: null,
        instructions: null,
      },
    ]);
  });

  it("blocks the same medicine being listed twice", async () => {
    get.mockResolvedValue(PATIENT);
    routeFor(<Prescribe />, "/doctor/patients/p1/prescribe");

    await userEvent.type(await screen.findByLabelText(/^medicine/i), "Metformin");
    await userEvent.type(screen.getByLabelText(/^dose/i), "500 mg");
    await userEvent.type(screen.getByLabelText(/^frequency/i), "Twice daily");

    await userEvent.click(screen.getByRole("button", { name: /add medicine/i }));

    // Each line repeats the same labels, so target the second set by index.
    await userEvent.type(screen.getAllByLabelText(/^medicine/i)[1], "metformin");
    await userEvent.type(screen.getAllByLabelText(/^dose/i)[1], "850 mg");
    await userEvent.type(screen.getAllByLabelText(/^frequency/i)[1], "Once daily");

    expect(
      await screen.findByText(/same medicine is listed twice/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /issue prescription/i })).toBeDisabled();
  });

  it("states that the AI does not prescribe", async () => {
    get.mockResolvedValue(PATIENT);
    routeFor(<Prescribe />, "/doctor/patients/p1/prescribe");

    expect(
      await screen.findByText(/decision support only — it does\s+not prescribe/i),
    ).toBeInTheDocument();
  });
});
