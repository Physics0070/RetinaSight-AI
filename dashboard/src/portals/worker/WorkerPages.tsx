/**
 * Remaining health-worker pages: patient list, screening history, referrals,
 * follow-ups, sync queue and profile.
 *
 * They share a list/table idiom deliberately — a field worker should learn one
 * pattern, not six.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/app/PageHeader";
import { ConnectivityBanner, useConnectivity } from "@/app/Connectivity";
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
import { useAuth } from "@/lib/auth";
import { useMutation, useQuery } from "@/lib/useApi";
import type {
  FollowUp,
  Page,
  Patient,
  Referral,
  ScreeningSession,
  SyncQueueEntry,
} from "@/lib/types";
import { ScreeningStateChip } from "./ScreeningStateChip";
import { formatDate, formatDateTime } from "./WorkerDashboard";

/* -------------------------------------------------------------------------- */
/* Patients                                                                    */
/* -------------------------------------------------------------------------- */
export function WorkerPatients() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  const patients = useQuery(
    (signal) =>
      api.get<Page<Patient>>("/patients", { query: query || undefined, page_size: 50 }, signal),
    [query],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Patients"
        subtitle="Search by name or patient code."
        actions={
          <Link to="/user/patients/new">
            <Button variant="primary">Register patient</Button>
          </Link>
        }
      />

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
        }}
      >
        <div className="min-w-[16rem] flex-1">
          <Field label="Search" htmlFor="patient-search">
            <Input
              id="patient-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name or code"
            />
          </Field>
        </div>
        <Button type="submit">Search</Button>
      </form>

      {patients.loading && <LoadingState label="Loading patients" />}
      {patients.error && (
        <ErrorState
          message={patients.error.message}
          offline={patients.error.isOffline}
          onRetry={patients.refetch}
        />
      )}

      {patients.data && patients.data.items.length === 0 && (
        <EmptyState
          title="No patients yet"
          description="Register a patient to begin their first screening."
          action={
            <Link to="/user/patients/new">
              <Button variant="primary">Register patient</Button>
            </Link>
          }
        />
      )}

      {patients.data && patients.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Registered patients">
            <thead>
              <tr>
                <Th>Patient</Th>
                <Th>Code</Th>
                <Th>Diabetes</Th>
                <Th>Registered</Th>
                <Th>Action</Th>
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
                    {patient.has_diabetes === null ? (
                      <span style={{ color: "var(--rs-ink-subtle)" }}>Unknown</span>
                    ) : patient.has_diabetes ? (
                      <Badge tone="warn">Yes</Badge>
                    ) : (
                      <Badge>No</Badge>
                    )}
                  </Td>
                  <Td>{formatDate(patient.created_at)}</Td>
                  <Td>
                    <StartScreeningButton patientId={patient.id} />
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

function StartScreeningButton({ patientId }: { patientId: string }) {
  const start = useMutation(async () => {
    const session = await api.post<ScreeningSession>("/screenings", {
      patient_id: patientId,
    });
    window.location.assign(`/user/screening/${session.id}`);
    return session;
  });

  return (
    <div className="flex flex-col gap-1">
      <Button size="sm" loading={start.loading} onClick={() => void start.run()}>
        Start screening
      </Button>
      {start.error && (
        <span className="text-[var(--rs-text-2xs)]" style={{ color: "var(--rs-danger)" }}>
          {start.error.message}
        </span>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Screening history                                                           */
/* -------------------------------------------------------------------------- */
export function WorkerScreenings() {
  const screenings = useQuery(
    (signal) => api.get<Page<ScreeningSession>>("/screenings", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Screenings" subtitle="Every screening you have conducted." />

      {screenings.loading && <LoadingState label="Loading screenings" />}
      {screenings.error && (
        <ErrorState
          message={screenings.error.message}
          offline={screenings.error.isOffline}
          onRetry={screenings.refetch}
        />
      )}

      {screenings.data?.items.length === 0 && (
        <EmptyState title="No screenings yet" description="Your completed screenings appear here." />
      )}

      {screenings.data && screenings.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Screening history">
            <thead>
              <tr>
                <Th>State</Th>
                <Th>Started</Th>
                <Th>Sync</Th>
                <Th>Action</Th>
              </tr>
            </thead>
            <tbody>
              {screenings.data.items.map((session) => (
                <tr key={session.id}>
                  <Td>
                    <ScreeningStateChip state={session.state} />
                  </Td>
                  <Td>{formatDateTime(session.started_at ?? session.created_at)}</Td>
                  <Td>
                    {session.sync_status === "synced" ? (
                      <Badge tone="ok">Synced</Badge>
                    ) : (
                      <Badge tone="warn">Pending</Badge>
                    )}
                  </Td>
                  <Td>
                    <Link to={`/user/screening/${session.id}`}>
                      <Button size="sm">Open</Button>
                    </Link>
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
/* Referrals                                                                   */
/* -------------------------------------------------------------------------- */
export function WorkerReferrals() {
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Referrals" subtitle="Cases sent onward for specialist attention." />

      {referrals.loading && <LoadingState label="Loading referrals" />}
      {referrals.error && (
        <ErrorState
          message={referrals.error.message}
          offline={referrals.error.isOffline}
          onRetry={referrals.refetch}
        />
      )}
      {referrals.data?.items.length === 0 && (
        <EmptyState title="No referrals" description="Referrals you create will appear here." />
      )}

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

export function PriorityBadge({ priority }: { priority: string }) {
  const tone =
    priority === "urgent" ? "danger" : priority === "consultation" ? "warn" : "neutral";
  const glyph = priority === "urgent" ? "●" : priority === "consultation" ? "◐" : "○";
  return (
    <Badge tone={tone as "danger" | "warn" | "neutral"} icon={<span aria-hidden="true">{glyph}</span>}>
      {priority}
    </Badge>
  );
}

/* -------------------------------------------------------------------------- */
/* Follow-ups                                                                  */
/* -------------------------------------------------------------------------- */
export function WorkerFollowUps() {
  const followUps = useQuery(
    (signal) => api.get<Page<FollowUp>>("/followups", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Follow-ups" subtitle="Patients due to be seen again." />

      {followUps.loading && <LoadingState label="Loading follow-ups" />}
      {followUps.error && (
        <ErrorState
          message={followUps.error.message}
          offline={followUps.error.isOffline}
          onRetry={followUps.refetch}
        />
      )}
      {followUps.data?.items.length === 0 && (
        <EmptyState title="No follow-ups scheduled" />
      )}

      {followUps.data && followUps.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Scheduled follow-ups">
            <thead>
              <tr>
                <Th>Due</Th>
                <Th>Status</Th>
                <Th>Instructions</Th>
              </tr>
            </thead>
            <tbody>
              {followUps.data.items.map((item) => {
                const overdue =
                  item.status === "scheduled" && item.due_date < new Date().toISOString().slice(0, 10);
                return (
                  <tr key={item.id}>
                    <Td>
                      <span className="rs-numeric">{formatDate(item.due_date)}</span>
                      {overdue && (
                        <span className="ml-2">
                          <Badge tone="warn">Overdue</Badge>
                        </span>
                      )}
                    </Td>
                    <Td>{item.status}</Td>
                    <Td>{item.instructions || "—"}</Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Sync queue                                                                  */
/* -------------------------------------------------------------------------- */
export function SyncQueuePage() {
  const online = useConnectivity();
  const status = useQuery(
    (signal) => api.get<{ counts: Record<string, number> }>("/sync/status", undefined, signal),
    [],
  );
  const queue = useQuery(
    (signal) => api.get<SyncQueueEntry[]>("/sync/queue", { limit: 100 }, signal),
    [],
  );

  const counts = status.data?.counts ?? {};
  const pending = (counts.pending ?? 0) + (counts.retrying ?? 0);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Sync queue"
        subtitle="Work captured offline and its synchronisation state."
        actions={
          <Button
            onClick={() => {
              status.refetch();
              queue.refetch();
            }}
          >
            Refresh
          </Button>
        }
      />

      {!online && <ConnectivityBanner pendingCount={pending} />}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Waiting" value={pending} tone={pending ? "warn" : "neutral"} />
        <Metric label="Synced" value={counts.synced ?? 0} tone="ok" />
        <Metric
          label="Failed"
          value={counts.failed ?? 0}
          tone={(counts.failed ?? 0) > 0 ? "danger" : "neutral"}
        />
        <Metric label="Uploading" value={counts.uploading ?? 0} />
      </section>

      {queue.loading && <LoadingState label="Loading queue" />}
      {queue.error && (
        <ErrorState message={queue.error.message} offline={queue.error.isOffline} />
      )}
      {queue.data?.length === 0 && (
        <EmptyState
          title="Nothing waiting to sync"
          description="Everything captured on this device has reached the server."
        />
      )}

      {queue.data && queue.data.length > 0 && (
        <Panel padded={false}>
          <Table caption="Sync queue items">
            <thead>
              <tr>
                <Th>Item</Th>
                <Th>Operation</Th>
                <Th>Status</Th>
                <Th>Attempts</Th>
                <Th>Last attempt</Th>
              </tr>
            </thead>
            <tbody>
              {queue.data.map((item) => (
                <tr key={item.id}>
                  <Td>{item.entity_type.replace(/_/g, " ")}</Td>
                  <Td>{item.operation}</Td>
                  <Td>
                    <SyncStatusBadge status={item.status} error={item.last_error} />
                  </Td>
                  <Td>
                    <span className="rs-numeric">{item.attempt_count}</span>
                  </Td>
                  <Td>{formatDateTime(item.last_attempt_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

function SyncStatusBadge({ status, error }: { status: string; error: string | null }) {
  const tone =
    status === "synced" ? "ok" : status === "failed" ? "danger" : "warn";
  return (
    <div className="flex flex-col gap-0.5">
      <Badge tone={tone as "ok" | "danger" | "warn"}>{status}</Badge>
      {error && (
        <span className="text-[var(--rs-text-2xs)]" style={{ color: "var(--rs-ink-subtle)" }}>
          {error}
        </span>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Profile                                                                     */
/* -------------------------------------------------------------------------- */
export function WorkerProfile() {
  const { user } = useAuth();

  return (
    <div className="flex max-w-xl flex-col gap-5">
      <PageHeader title="Profile" />
      <Panel className="flex flex-col gap-3">
        <ProfileRow label="Name" value={user?.full_name} />
        <ProfileRow label="Email" value={user?.email} />
        <ProfileRow label="Role" value="Health worker" />
        <ProfileRow label="Status" value={user?.status} />
      </Panel>
    </div>
  );
}

export function ProfileRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="rs-label">{label}</span>
      <span className="text-[var(--rs-text-sm)]">{value ?? "—"}</span>
    </div>
  );
}
