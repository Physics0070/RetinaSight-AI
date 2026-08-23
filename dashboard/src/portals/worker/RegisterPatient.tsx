/**
 * Patient registration.
 *
 * Consent first, then only the details screening and referral actually need.
 * Screening cannot begin until consent is recorded — the backend enforces this
 * too, so the checkbox is a UI reflection of a real rule.
 */

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import {
  Button,
  ErrorState,
  Field,
  Input,
  Panel,
  Select,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useMutation } from "@/lib/useApi";
import type { Patient, ScreeningSession } from "@/lib/types";

export function RegisterPatient() {
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [sex, setSex] = useState("");
  const [phone, setPhone] = useState("");
  const [hasDiabetes, setHasDiabetes] = useState("");
  const [duration, setDuration] = useState("");
  const [screeningConsent, setScreeningConsent] = useState(false);
  const [storageConsent, setStorageConsent] = useState(false);

  const register = useMutation(async () => {
    const patient = await api.post<Patient>("/patients", {
      full_name: fullName.trim(),
      date_of_birth: dateOfBirth || null,
      sex: sex || null,
      phone: phone.trim() || null,
      has_diabetes: hasDiabetes === "" ? null : hasDiabetes === "yes",
      diabetes_duration_years: duration ? Number(duration) : null,
      consents: [
        { consent_type: "screening", granted: screeningConsent },
        { consent_type: "data_storage", granted: storageConsent },
      ],
    });

    const session = await api.post<ScreeningSession>("/screenings", {
      patient_id: patient.id,
    });
    navigate(`/user/screening/${session.id}`);
    return patient;
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void register.run();
  };

  const canSubmit = fullName.trim().length > 0 && screeningConsent;

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <PageHeader
        title="Register patient"
        subtitle="Record consent, then capture the essentials."
        backTo="/user/patients"
        backLabel="Patients"
      />

      <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
        {/* Consent leads the form — it gates everything that follows. */}
        <Panel className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="rs-label">Step 1 · Consent</span>
            <h2 className="text-[var(--rs-text-lg)] font-semibold">Explain and record consent</h2>
          </div>

          <ConsentCheckbox
            id="consent-screening"
            checked={screeningConsent}
            onChange={setScreeningConsent}
            title="Consent to retinal screening"
            description="The patient agrees to have photographs taken of the back of their eyes for diabetic retinopathy screening."
            required
          />
          <ConsentCheckbox
            id="consent-storage"
            checked={storageConsent}
            onChange={setStorageConsent}
            title="Consent to secure data storage"
            description="Images and results are stored securely and shared with the reviewing clinician."
          />

          {!screeningConsent && (
            <p className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
              Screening consent is required before any image can be captured.
            </p>
          )}
        </Panel>

        <Panel className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="rs-label">Step 2 · Patient details</span>
            <h2 className="text-[var(--rs-text-lg)] font-semibold">Basic information</h2>
          </div>

          <Field label="Full name" htmlFor="full-name" required>
            <Input
              id="full-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              required
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Date of birth" htmlFor="dob">
              <Input
                id="dob"
                type="date"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
              />
            </Field>
            <Field label="Sex" htmlFor="sex">
              <Select id="sex" value={sex} onChange={(e) => setSex(e.target.value)}>
                <option value="">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
                <option value="other">Other</option>
              </Select>
            </Field>
          </div>

          <Field label="Phone" htmlFor="phone" hint="Used for follow-up reminders.">
            <Input
              id="phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              autoComplete="tel"
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Diagnosed with diabetes" htmlFor="diabetes">
              <Select
                id="diabetes"
                value={hasDiabetes}
                onChange={(e) => setHasDiabetes(e.target.value)}
              >
                <option value="">Unknown</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </Select>
            </Field>
            {hasDiabetes === "yes" && (
              <Field label="Years since diagnosis" htmlFor="duration">
                <Input
                  id="duration"
                  type="number"
                  min={0}
                  max={120}
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                />
              </Field>
            )}
          </div>
        </Panel>

        {register.error && (
          <ErrorState message={register.error.message} offline={register.error.isOffline} />
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            variant="primary"
            size="lg"
            loading={register.loading}
            disabled={!canSubmit}
          >
            Save and start screening
          </Button>
          <Button type="button" variant="ghost" onClick={() => navigate("/user/patients")}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}

function ConsentCheckbox({
  id,
  checked,
  onChange,
  title,
  description,
  required,
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  title: string;
  description: string;
  required?: boolean;
}) {
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-start gap-3 rounded-[var(--rs-radius-md)] border p-3"
      style={{
        borderColor: checked ? "var(--rs-accent)" : "var(--rs-line)",
        background: checked
          ? "color-mix(in srgb, var(--rs-accent) 8%, transparent)"
          : "transparent",
      }}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        required={required}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 h-5 w-5 shrink-0"
      />
      <span className="flex flex-col gap-0.5">
        <span className="text-[var(--rs-text-sm)] font-semibold">
          {title}
          {required && (
            <span aria-hidden="true" style={{ color: "var(--rs-danger)" }}>
              {" *"}
            </span>
          )}
        </span>
        <span className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
          {description}
        </span>
      </span>
    </label>
  );
}
