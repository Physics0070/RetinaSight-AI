/**
 * Write a prescription.
 *
 * The clinician composes the document line by line; nothing here is suggested
 * or pre-filled by the model. The AI screens and explains — a licensed
 * clinician decides and signs, and the API records who that was.
 */

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Panel,
  Textarea,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/useApi";
import type { Patient, Prescription, PrescriptionItem } from "@/lib/types";

type DraftItem = {
  name: string;
  dose: string;
  frequency: string;
  duration: string;
  instructions: string;
};

const EMPTY_ITEM: DraftItem = {
  name: "",
  dose: "",
  frequency: "",
  duration: "",
  instructions: "",
};

export function Prescribe() {
  const { patientId = "" } = useParams();
  const navigate = useNavigate();

  const patient = useQuery(
    (signal) => api.get<Patient>(`/patients/${patientId}`, undefined, signal),
    [patientId],
  );

  const [items, setItems] = useState<DraftItem[]>([{ ...EMPTY_ITEM }]);
  const [diagnosis, setDiagnosis] = useState("");
  const [notes, setNotes] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const patch = (index: number, change: Partial<DraftItem>) =>
    setItems((current) =>
      current.map((item, i) => (i === index ? { ...item, ...change } : item)),
    );

  const addLine = () => setItems((current) => [...current, { ...EMPTY_ITEM }]);
  const removeLine = (index: number) =>
    setItems((current) => current.filter((_, i) => i !== index));

  // A line counts once it names a drug with a dose and a frequency — the three
  // things without which a prescription cannot be dispensed.
  const completeItems = items.filter(
    (item) => item.name.trim() && item.dose.trim() && item.frequency.trim(),
  );
  const duplicated =
    new Set(completeItems.map((i) => i.name.trim().toLowerCase())).size !==
    completeItems.length;
  const canSubmit = completeItems.length > 0 && !duplicated && !busy;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setProblem(null);
    try {
      const payload = {
        diagnosis: diagnosis.trim() || null,
        notes: notes.trim() || null,
        valid_until: validUntil || null,
        items: completeItems.map<PrescriptionItem>((item) => ({
          name: item.name.trim(),
          dose: item.dose.trim(),
          frequency: item.frequency.trim(),
          duration: item.duration.trim() || null,
          instructions: item.instructions.trim() || null,
        })),
      };
      await api.post<Prescription>(`/patients/${patientId}/prescriptions`, payload);
      navigate(`/doctor/patients/${patientId}`);
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Prescribe medicine"
        subtitle={
          patient.data
            ? `For ${patient.data.full_name} · ${patient.data.patient_code}`
            : "Loading patient…"
        }
      />

      {patient.loading && <LoadingState label="Loading patient" />}
      {patient.error && (
        <ErrorState message={patient.error.message} onRetry={patient.refetch} />
      )}
      {problem && <ErrorState message={problem} />}

      <form className="flex flex-col gap-5" onSubmit={submit}>
        <Panel className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Diagnosis"
              htmlFor="rx-diagnosis"
              hint="What this prescription treats"
            >
              <Input
                id="rx-diagnosis"
                value={diagnosis}
                onChange={(e) => setDiagnosis(e.target.value)}
                placeholder="Moderate non-proliferative diabetic retinopathy"
              />
            </Field>
            <Field label="Valid until" htmlFor="rx-valid" hint="Optional">
              <Input
                id="rx-valid"
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            </Field>
          </div>
        </Panel>

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-[var(--rs-text-lg)] font-bold">Medicines</h2>
            <Button type="button" onClick={addLine}>
              Add medicine
            </Button>
          </div>

          {items.map((item, index) => (
            <Panel key={index} className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-3">
                <span className="rs-label">Medicine {index + 1}</span>
                {items.length > 1 && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => removeLine(index)}
                    aria-label={`Remove medicine ${index + 1}`}
                  >
                    Remove
                  </Button>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Medicine" htmlFor={`rx-name-${index}`} required>
                  <Input
                    id={`rx-name-${index}`}
                    value={item.name}
                    onChange={(e) => patch(index, { name: e.target.value })}
                    placeholder="Metformin"
                  />
                </Field>
                <Field label="Dose" htmlFor={`rx-dose-${index}`} required>
                  <Input
                    id={`rx-dose-${index}`}
                    value={item.dose}
                    onChange={(e) => patch(index, { dose: e.target.value })}
                    placeholder="500 mg"
                  />
                </Field>
                <Field label="Frequency" htmlFor={`rx-freq-${index}`} required>
                  <Input
                    id={`rx-freq-${index}`}
                    value={item.frequency}
                    onChange={(e) => patch(index, { frequency: e.target.value })}
                    placeholder="Twice daily"
                  />
                </Field>
                <Field label="Duration" htmlFor={`rx-duration-${index}`}>
                  <Input
                    id={`rx-duration-${index}`}
                    value={item.duration}
                    onChange={(e) => patch(index, { duration: e.target.value })}
                    placeholder="3 months"
                  />
                </Field>
              </div>

              <Field label="Instructions" htmlFor={`rx-instructions-${index}`}>
                <Input
                  id={`rx-instructions-${index}`}
                  value={item.instructions}
                  onChange={(e) => patch(index, { instructions: e.target.value })}
                  placeholder="With food."
                />
              </Field>
            </Panel>
          ))}

          {duplicated && (
            <ErrorState message="The same medicine is listed twice. Combine the lines or change one of them." />
          )}
        </section>

        <Panel className="flex flex-col gap-4">
          <Field label="Notes" htmlFor="rx-notes" hint="Shown with the prescription">
            <Textarea
              id="rx-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Review after retinal photography in 3 months."
            />
          </Field>

          <p className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
            This prescription is recorded against your account as the prescribing
            clinician. The AI screening result is decision support only — it does
            not prescribe.
          </p>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" size="lg" loading={busy} disabled={!canSubmit}>
              Issue prescription
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="lg"
              onClick={() => navigate(`/doctor/patients/${patientId}`)}
            >
              Cancel
            </Button>
          </div>
        </Panel>
      </form>
    </div>
  );
}
