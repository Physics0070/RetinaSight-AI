/** Admin: clinics, patients, screenings, referrals, audit log, system health. */

import { useState } from "react";

import { PageHeader } from "@/app/PageHeader";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Metric,
  Panel,
  Table,
  Td,
  Th,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useMutation, useQuery } from "@/lib/useApi";
import type {
  AuditLogEntry,
  Clinic,
  Page,
  Patient,
  Referral,
  ScreeningSession,
  SystemHealth,
} from "@/lib/types";
import { ScreeningStateChip } from "@/portals/worker/ScreeningStateChip";
import { PriorityBadge } from "@/portals/worker/WorkerPages";
import { formatDate, formatDateTime } from "@/portals/worker/WorkerDashboard";

/* -------------------------------------------------------------------------- */
export function AdminClinics() {
  const [creating, setCreating] = useState(false);
  const clinics = useQuery(
    (signal) => api.get<Page<Clinic>>("/clinics", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Clinics"
        subtitle="Sites where screening takes place."
        actions={
          <Button variant="primary" onClick={() => setCreating((v) => !v)}>
            {creating ? "Close" : "Add clinic"}
          </Button>
        }
      />

      {creating && (
        <CreateClinicForm
          onCreated={() => {
            setCreating(false);
            clinics.refetch();
          }}
        />
      )}

      {clinics.loading && <LoadingState label="Loading clinics" />}
      {clinics.error && <ErrorState message={clinics.error.message} onRetry={clinics.refetch} />}
      {clinics.data?.items.length === 0 && (
        <EmptyState
          title="No clinics yet"
          description="Add a clinic so staff and screenings can be assigned to it."
        />
      )}

      {clinics.data && clinics.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Clinics">
            <thead>
              <tr>
                <Th>Clinic</Th>
                <Th>Location</Th>
                <Th>Health workers</Th>
                <Th>Doctors</Th>
                <Th>Screenings</Th>
                <Th>Open referrals</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {clinics.data.items.map((clinic) => (
                <tr key={clinic.id}>
                  <Td>
                    <div className="flex flex-col">
                      <span className="font-semibold">{clinic.name}</span>
                      <span className="rs-numeric text-[var(--rs-text-xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
                        {clinic.code}
                      </span>
                    </div>
                  </Td>
                  <Td>{clinic.location || "—"}</Td>
                  <Td>
                    <span className="rs-numeric">{clinic.health_worker_count}</span>
                  </Td>
                  <Td>
                    <span className="rs-numeric">{clinic.doctor_count}</span>
                  </Td>
                  <Td>
                    <span className="rs-numeric">{clinic.screening_count}</span>
                  </Td>
                  <Td>
                    <span className="rs-numeric">{clinic.pending_referrals}</span>
                  </Td>
                  <Td>
                    <Badge tone={clinic.status === "active" ? "ok" : "warn"}>
                      {clinic.status}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

function CreateClinicForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [location, setLocation] = useState("");

  const create = useMutation(async () => {
    await api.post("/clinics", {
      name: name.trim(),
      code: code.trim(),
      location: location.trim(),
    });
    onCreated();
  });

  return (
    <Panel className="flex flex-col gap-4">
      <h2 className="rs-label">Add a clinic</h2>
      <form
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
          void create.run();
        }}
      >
        <Field label="Name" htmlFor="clinic-name" required>
          <Input id="clinic-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Code" htmlFor="clinic-code" required>
          <Input id="clinic-code" value={code} onChange={(e) => setCode(e.target.value)} required />
        </Field>
        <Field label="Location" htmlFor="clinic-location">
          <Input
            id="clinic-location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </Field>
        <div className="flex items-end">
          <Button type="submit" variant="primary" loading={create.loading}>
            Add clinic
          </Button>
        </div>
        <div className="sm:col-span-2 xl:col-span-4">
          {create.error && <ErrorState message={create.error.message} />}
        </div>
      </form>
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
export function AdminPatients() {
  const patients = useQuery(
    (signal) => api.get<Page<Patient>>("/patients", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Patients" subtitle="All registered patients." />

      {patients.loading && <LoadingState label="Loading patients" />}
      {patients.error && <ErrorState message={patients.error.message} onRetry={patients.refetch} />}
      {patients.data?.items.length === 0 && <EmptyState title="No patients registered" />}

      {patients.data && patients.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Patients">
            <thead>
              <tr>
                <Th>Patient</Th>
                <Th>Code</Th>
                <Th>Diabetes</Th>
                <Th>Registered</Th>
              </tr>
            </thead>
            <tbody>
              {patients.data.items.map((patient) => (
                <tr key={patient.id}>
                  <Td>
                    <span className="font-semibold">{patient.full_name}</span>
                  </Td>
                  <Td>
                    <span className="rs-numeric">{patient.patient_code}</span>
                  </Td>
                  <Td>
                    {patient.has_diabetes === null
                      ? "Unknown"
                      : patient.has_diabetes
                        ? "Yes"
                        : "No"}
                  </Td>
                  <Td>{formatDate(patient.created_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function AdminScreenings() {
  const screenings = useQuery(
    (signal) => api.get<Page<ScreeningSession>>("/screenings", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Screenings" subtitle="All screening sessions across clinics." />

      {screenings.loading && <LoadingState label="Loading screenings" />}
      {screenings.error && (
        <ErrorState message={screenings.error.message} onRetry={screenings.refetch} />
      )}
      {screenings.data?.items.length === 0 && <EmptyState title="No screenings recorded" />}

      {screenings.data && screenings.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Screenings">
            <thead>
              <tr>
                <Th>State</Th>
                <Th>Started</Th>
                <Th>Offline</Th>
                <Th>Sync</Th>
              </tr>
            </thead>
            <tbody>
              {screenings.data.items.map((session) => (
                <tr key={session.id}>
                  <Td>
                    <ScreeningStateChip state={session.state} />
                  </Td>
                  <Td>{formatDateTime(session.started_at ?? session.created_at)}</Td>
                  <Td>{session.captured_offline ? "Yes" : "No"}</Td>
                  <Td>
                    <Badge tone={session.sync_status === "synced" ? "ok" : "warn"}>
                      {session.sync_status}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function AdminReferrals() {
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Referrals" subtitle="Referrals raised across the platform." />

      {referrals.loading && <LoadingState label="Loading referrals" />}
      {referrals.error && (
        <ErrorState message={referrals.error.message} onRetry={referrals.refetch} />
      )}
      {referrals.data?.items.length === 0 && <EmptyState title="No referrals" />}

      {referrals.data && referrals.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Referrals">
            <thead>
              <tr>
                <Th>Priority</Th>
                <Th>Status</Th>
                <Th>Reason</Th>
                <Th>Created</Th>
              </tr>
            </thead>
            <tbody>
              {referrals.data.items.map((referral) => (
                <tr key={referral.id}>
                  <Td>
                    <PriorityBadge priority={referral.priority} />
                  </Td>
                  <Td>{referral.status}</Td>
                  <Td>{referral.reason || "—"}</Td>
                  <Td>{formatDate(referral.created_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function AdminAudit() {
  const [action, setAction] = useState("");
  const [applied, setApplied] = useState("");

  const logs = useQuery(
    (signal) =>
      api.get<Page<AuditLogEntry>>(
        "/audit",
        { action: applied || undefined, page_size: 100 },
        signal,
      ),
    [applied],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Audit log"
        subtitle="Who did what, and when. Patient data is deliberately excluded."
      />

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(action.trim());
        }}
      >
        <div className="min-w-[16rem]">
          <Field label="Filter by action" htmlFor="audit-action">
            <Input
              id="audit-action"
              value={action}
              onChange={(e) => setAction(e.target.value)}
              placeholder="e.g. login, referral_created"
            />
          </Field>
        </div>
        <Button type="submit">Apply</Button>
      </form>

      {logs.loading && <LoadingState label="Loading audit log" />}
      {logs.error && <ErrorState message={logs.error.message} onRetry={logs.refetch} />}
      {logs.data?.items.length === 0 && <EmptyState title="No audit entries match" />}

      {logs.data && logs.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Audit log">
            <thead>
              <tr>
                <Th>Timestamp</Th>
                <Th>Actor</Th>
                <Th>Role</Th>
                <Th>Action</Th>
                <Th>Resource</Th>
                <Th>Result</Th>
              </tr>
            </thead>
            <tbody>
              {logs.data.items.map((entry) => (
                <tr key={entry.id}>
                  <Td>{formatDateTime(entry.created_at)}</Td>
                  <Td>{entry.actor_email ?? "—"}</Td>
                  <Td>{entry.actor_role ?? "—"}</Td>
                  <Td>{entry.action.replace(/_/g, " ")}</Td>
                  <Td>{entry.resource_type?.replace(/_/g, " ") ?? "—"}</Td>
                  <Td>
                    <Badge
                      tone={
                        entry.result === "success"
                          ? "ok"
                          : entry.result === "denied"
                            ? "warn"
                            : "danger"
                      }
                    >
                      {entry.result}
                    </Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
export function AdminSystemHealth() {
  const health = useQuery(
    (signal) => api.get<SystemHealth>("/admin/system-health", undefined, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="System health"
        subtitle="Live dependency checks."
        actions={<Button onClick={health.refetch}>Re-check</Button>}
      />

      {health.loading && <LoadingState label="Checking system" />}
      {health.error && <ErrorState message={health.error.message} onRetry={health.refetch} />}

      {health.data && (
        <>
          <section className="grid gap-3 sm:grid-cols-3">
            <Metric
              label="Database"
              value={health.data.database.ok ? "Connected" : "Unavailable"}
              hint={health.data.database.engine}
              tone={health.data.database.ok ? "ok" : "danger"}
            />
            <Metric
              label="Object storage"
              value={health.data.storage.ok ? "Available" : "Unavailable"}
              hint={health.data.storage.provider}
              tone={health.data.storage.ok ? "ok" : "danger"}
            />
            <Metric
              label="Screening model"
              value={health.data.model.ok ? "Loaded" : "Unavailable"}
              hint={health.data.model.version}
              tone={health.data.model.ok ? "ok" : "danger"}
            />
          </section>

          <Panel className="flex flex-col gap-2">
            <span className="rs-label">Model status</span>
            <div className="flex flex-wrap gap-2">
              {health.data.model.development && <Badge tone="warn">Development model</Badge>}
              <Badge
                tone={health.data.model.validation_status === "validated" ? "ok" : "warn"}
              >
                {health.data.model.validation_status.replace(/_/g, " ")}
              </Badge>
              <Badge>{health.data.environment}</Badge>
            </div>
            {health.data.model.development && (
              <p className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
                A development placeholder is serving inference. It produces no
                clinically meaningful output.
              </p>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
