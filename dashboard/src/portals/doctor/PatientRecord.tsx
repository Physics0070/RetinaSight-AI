/**
 * Patient clinical record — the doctor's view of one patient.
 *
 * Two things live here: the medical history (typed entries the clinician can
 * add, correct and retire) and the prescriptions written for this patient.
 *
 * History entries are *retired*, never destroyed — the API soft-deletes, so a
 * correction leaves the original recorded. The UI says "Remove" but is honest
 * in the confirm text about what actually happens.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Panel,
  Select,
  Textarea,
  cx,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useQuery } from "@/lib/useApi";
import type {
  HistoryEntry,
  HistoryEntryType,
  Patient,
  Prescription,
} from "@/lib/types";

const ENTRY_TYPES: { value: HistoryEntryType; label: string }[] = [
  { value: "condition", label: "Condition" },
  { value: "medication", label: "Medication" },
  { value: "allergy", label: "Allergy" },
  { value: "procedure", label: "Procedure" },
  { value: "family_history", label: "Family history" },
  { value: "observation", label: "Observation" },
  { value: "note", label: "Note" },
];

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  ENTRY_TYPES.map((t) => [t.value, t.label]),
);

/** An allergy is the one entry type that must never be skimmed past. */
function toneFor(type: string): "neutral" | "danger" | "warn" | "info" {
  if (type === "allergy") return "danger";
  if (type === "condition") return "warn";
  if (type === "medication") return "info";
  return "neutral";
}

interface DraftEntry {
  entry_type: HistoryEntryType;
  title: string;
  detail: string;
  occurred_on: string;
  status: string;
}

const EMPTY_DRAFT: DraftEntry = {
  entry_type: "condition",
  title: "",
  detail: "",
  occurred_on: "",
  status: "",
};

export function PatientRecord() {
  const { patientId = "" } = useParams();

  const patient = useQuery(
    (signal) => api.get<Patient>(`/patients/${patientId}`, undefined, signal),
    [patientId],
  );
  const history = useQuery(
    (signal) => api.get<HistoryEntry[]>(`/patients/${patientId}/history`, undefined, signal),
    [patientId],
  );
  const prescriptions = useQuery(
    (signal) =>
      api.get<Prescription[]>(`/patients/${patientId}/prescriptions`, undefined, signal),
    [patientId],
  );

  const [draft, setDraft] = useState<DraftEntry>(EMPTY_DRAFT);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<DraftEntry>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const payloadFrom = (d: DraftEntry) => ({
    entry_type: d.entry_type,
    title: d.title.trim(),
    detail: d.detail.trim() || null,
    occurred_on: d.occurred_on || null,
    status: d.status.trim() || null,
  });

  const submitNew = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.title.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      await api.post(`/patients/${patientId}/history`, payloadFrom(draft));
      setDraft(EMPTY_DRAFT);
      setAdding(false);
      history.refetch();
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const beginEdit = (entry: HistoryEntry) => {
    setEditingId(entry.id);
    setEditDraft({
      entry_type: entry.entry_type,
      title: entry.title,
      detail: entry.detail ?? "",
      occurred_on: entry.occurred_on ?? "",
      status: entry.status ?? "",
    });
  };

  const saveEdit = async (entryId: string) => {
    setBusy(true);
    setProblem(null);
    try {
      await api.patch(`/history/${entryId}`, payloadFrom(editDraft));
      setEditingId(null);
      history.refetch();
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const removeEntry = async (entry: HistoryEntry) => {
    const ok = window.confirm(
      `Retire "${entry.title}" from the active history?\n\n` +
        "It stays in the record for audit — it is hidden, not deleted.",
    );
    if (!ok) return;
    setBusy(true);
    setProblem(null);
    try {
      await api.del(`/history/${entry.id}`);
      history.refetch();
    } catch (error) {
      setProblem((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={patient.data?.full_name ?? "Patient record"}
        subtitle="Medical history and prescriptions."
      />

      {patient.loading && <LoadingState label="Loading patient" />}
      {patient.error && (
        <ErrorState message={patient.error.message} onRetry={patient.refetch} />
      )}

      {patient.data && (
        <Panel className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <Detail label="Patient code" value={patient.data.patient_code} numeric />
          <Detail
            label="Diabetes"
            value={
              patient.data.has_diabetes === null
                ? "Unknown"
                : patient.data.has_diabetes
                  ? `Yes${
                      patient.data.diabetes_duration_years
                        ? ` · ${patient.data.diabetes_duration_years}y`
                        : ""
                    }`
                  : "No"
            }
          />
          <Detail label="Sex" value={patient.data.sex ?? "—"} />
          <Detail
            label="Date of birth"
            value={patient.data.date_of_birth ?? "—"}
            numeric
          />
          <div className="ml-auto">
            <Link to={`/doctor/patients/${patientId}/prescribe`}>
              <Button variant="primary">Prescribe medicine</Button>
            </Link>
          </div>
        </Panel>
      )}

      {problem && <ErrorState message={problem} />}

      {/* ---------------------------------------------------------------- */}
      {/* Medical history                                                   */}
      {/* ---------------------------------------------------------------- */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[var(--rs-text-lg)] font-bold">Medical history</h2>
          <Button
            variant={adding ? "ghost" : "secondary"}
            onClick={() => {
              setAdding((v) => !v);
              setProblem(null);
            }}
          >
            {adding ? "Cancel" : "Add entry"}
          </Button>
        </div>

        {adding && (
          <Panel>
            <form className="flex flex-col gap-4" onSubmit={submitNew}>
              <EntryFields
                idPrefix="new"
                draft={draft}
                onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))}
              />
              <div className="flex gap-2">
                <Button type="submit" variant="primary" loading={busy} disabled={!draft.title.trim()}>
                  Save entry
                </Button>
                <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </Panel>
        )}

        {history.loading && <LoadingState label="Loading history" />}
        {history.error && (
          <ErrorState message={history.error.message} onRetry={history.refetch} />
        )}
        {history.data?.length === 0 && !adding && (
          <Panel>
            <EmptyState
              title="No history recorded yet"
              description="Add conditions, medications, allergies and procedures to build this patient's record."
              action={<Button variant="primary" onClick={() => setAdding(true)}>Add the first entry</Button>}
            />
          </Panel>
        )}

        {history.data?.map((entry) =>
          editingId === entry.id ? (
            <Panel key={entry.id}>
              <div className="flex flex-col gap-4">
                <EntryFields
                  idPrefix={`edit-${entry.id}`}
                  draft={editDraft}
                  onChange={(patch) => setEditDraft((d) => ({ ...d, ...patch }))}
                />
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    loading={busy}
                    disabled={!editDraft.title.trim()}
                    onClick={() => void saveEdit(entry.id)}
                  >
                    Save changes
                  </Button>
                  <Button variant="ghost" onClick={() => setEditingId(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            </Panel>
          ) : (
            <Panel key={entry.id} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={toneFor(entry.entry_type)}>
                      {TYPE_LABEL[entry.entry_type] ?? entry.entry_type}
                    </Badge>
                    <span className="text-[var(--rs-text-base)] font-semibold">
                      {entry.title}
                    </span>
                    {entry.status && (
                      <span
                        className="text-[var(--rs-text-xs)]"
                        style={{ color: "var(--rs-ink-subtle)" }}
                      >
                        · {entry.status}
                      </span>
                    )}
                  </div>
                  {entry.detail && (
                    <p
                      className="max-w-3xl text-[var(--rs-text-sm)]"
                      style={{ color: "var(--rs-ink-muted)" }}
                    >
                      {entry.detail}
                    </p>
                  )}
                  <span
                    className="rs-numeric text-[var(--rs-text-2xs)]"
                    style={{ color: "var(--rs-ink-subtle)" }}
                  >
                    {entry.occurred_on ? `Occurred ${entry.occurred_on}` : "Date not recorded"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => beginEdit(entry)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void removeEntry(entry)}>
                    Remove
                  </Button>
                </div>
              </div>
            </Panel>
          ),
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Prescriptions                                                     */}
      {/* ---------------------------------------------------------------- */}
      <section className="flex flex-col gap-3">
        <h2 className="text-[var(--rs-text-lg)] font-bold">Prescriptions</h2>

        {prescriptions.loading && <LoadingState label="Loading prescriptions" />}
        {prescriptions.error && (
          <ErrorState message={prescriptions.error.message} onRetry={prescriptions.refetch} />
        )}
        {prescriptions.data?.length === 0 && (
          <Panel>
            <EmptyState
              title="No prescriptions"
              description="Nothing has been prescribed for this patient yet."
              action={
                <Link to={`/doctor/patients/${patientId}/prescribe`}>
                  <Button variant="primary">Prescribe medicine</Button>
                </Link>
              }
            />
          </Panel>
        )}

        {prescriptions.data?.map((rx) => (
          <Panel key={rx.id} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={rx.status === "active" ? "ok" : "neutral"}>{rx.status}</Badge>
                {rx.diagnosis && (
                  <span className="font-semibold">{rx.diagnosis}</span>
                )}
              </div>
              <span
                className="rs-numeric text-[var(--rs-text-2xs)]"
                style={{ color: "var(--rs-ink-subtle)" }}
              >
                {new Date(rx.created_at).toLocaleDateString()}
              </span>
            </div>
            <ul className="flex flex-col gap-1">
              {rx.items.map((item, index) => (
                <li key={`${item.name}-${index}`} className="text-[var(--rs-text-sm)]">
                  <span className="font-semibold">{item.name}</span>{" "}
                  <span style={{ color: "var(--rs-ink-muted)" }}>
                    {item.dose} · {item.frequency}
                    {item.duration ? ` · ${item.duration}` : ""}
                    {item.instructions ? ` — ${item.instructions}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            {rx.notes && (
              <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
                {rx.notes}
              </p>
            )}
          </Panel>
        ))}
      </section>
    </div>
  );
}

function Detail({
  label,
  value,
  numeric,
}: {
  label: string;
  value: string;
  numeric?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="rs-label">{label}</span>
      <span className={cx("text-[var(--rs-text-sm)] font-semibold", numeric && "rs-numeric")}>
        {value}
      </span>
    </div>
  );
}

/** The shared field set for adding and editing — one definition, two uses. */
function EntryFields({
  idPrefix,
  draft,
  onChange,
}: {
  idPrefix: string;
  draft: DraftEntry;
  onChange: (patch: Partial<DraftEntry>) => void;
}) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Type" htmlFor={`${idPrefix}-type`}>
          <Select
            id={`${idPrefix}-type`}
            value={draft.entry_type}
            onChange={(e) => onChange({ entry_type: e.target.value as HistoryEntryType })}
          >
            {ENTRY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Date" htmlFor={`${idPrefix}-date`} hint="When it happened, if known">
          <Input
            id={`${idPrefix}-date`}
            type="date"
            value={draft.occurred_on}
            onChange={(e) => onChange({ occurred_on: e.target.value })}
          />
        </Field>
        <Field label="Status" htmlFor={`${idPrefix}-status`} hint="e.g. ongoing, resolved">
          <Input
            id={`${idPrefix}-status`}
            value={draft.status}
            onChange={(e) => onChange({ status: e.target.value })}
            placeholder="ongoing"
          />
        </Field>
      </div>
      <Field label="Title" htmlFor={`${idPrefix}-title`} required>
        <Input
          id={`${idPrefix}-title`}
          value={draft.title}
          onChange={(e) => onChange({ title: e.target.value })}
          placeholder="Type 2 diabetes mellitus"
        />
      </Field>
      <Field label="Detail" htmlFor={`${idPrefix}-detail`}>
        <Textarea
          id={`${idPrefix}-detail`}
          value={draft.detail}
          onChange={(e) => onChange({ detail: e.target.value })}
          placeholder="Anything a reviewing clinician should know."
        />
      </Field>
    </>
  );
}
