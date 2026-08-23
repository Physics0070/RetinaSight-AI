/** Doctor portal: patients, referrals, reviews, follow-ups, activity, profile. */

import { useState } from "react";
import { Link } from "react-router-dom";

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
  Table,
  Td,
  Th,
} from "@/design-system/components/primitives";
import { RiskBadge } from "@/design-system/risk/RiskDisplay";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useQuery } from "@/lib/useApi";
import type {
  AuditLogEntry,
  FollowUp,
  Page,
  Patient,
  Referral,
  RiskQueueItem,
} from "@/lib/types";
import { PriorityBadge, ProfileRow } from "@/portals/worker/WorkerPages";
import { formatDate, formatDateTime } from "@/portals/worker/WorkerDashboard";

/* -------------------------------------------------------------------------- */
export function DoctorPatients() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  const patients = useQuery(
    (signal) =>
      api.get<Page<Patient>>("/patients", { query: query || undefined, page_size: 50 }, signal),
    [query],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Patients" subtitle="Patients under screening at your clinics." />

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
        }}
      >
        <div className="min-w-[16rem] flex-1">
          <Field label="Search" htmlFor="doctor-patient-search">
            <Input
              id="doctor-patient-search"
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
        <ErrorState message={patients.error.message} onRetry={patients.refetch} />
      )}
      {patients.data?.items.length === 0 && <EmptyState title="No patients found" />}

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
                        ? `Yes${
                            patient.diabetes_duration_years
                              ? ` · ${patient.diabetes_duration_years}y`
                              : ""
                          }`
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
export function DoctorReferrals() {
  const referrals = useQuery(
    (signal) => api.get<Page<Referral>>("/referrals", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Referrals" subtitle="Cases referred for specialist attention." />

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
export function DoctorReviews() {
  const reviews = useQuery(
    (signal) =>
      api.get<Page<RiskQueueItem>>("/reviews/queue", { status: "", page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Clinical reviews" subtitle="Every case you have seen or claimed." />

      {reviews.loading && <LoadingState label="Loading reviews" />}
      {reviews.error && <ErrorState message={reviews.error.message} onRetry={reviews.refetch} />}
      {reviews.data?.items.length === 0 && <EmptyState title="No reviews yet" />}

      {reviews.data && reviews.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Clinical reviews">
            <thead>
              <tr>
                <Th>Patient</Th>
                <Th>Risk</Th>
                <Th>Status</Th>
                <Th>Decision</Th>
                <Th>Reviewed</Th>
                <Th>Open</Th>
              </tr>
            </thead>
            <tbody>
              {reviews.data.items.map((item) => (
                <tr key={item.review.id}>
                  <Td>
                    <span className="font-semibold">{item.patient.full_name}</span>
                  </Td>
                  <Td>{item.risk ? <RiskBadge level={item.risk.risk_level} size="sm" /> : "—"}</Td>
                  <Td>
                    <Badge tone={item.review.status === "completed" ? "ok" : "warn"}>
                      {item.review.status.replace(/_/g, " ")}
                    </Badge>
                  </Td>
                  <Td>{item.review.decision?.replace(/_/g, " ") ?? "—"}</Td>
                  <Td>{formatDateTime(item.review.reviewed_at)}</Td>
                  <Td>
                    <Link to={`/doctor/reviews/${item.review.id}`}>
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
export function DoctorFollowUps() {
  const followUps = useQuery(
    (signal) => api.get<Page<FollowUp>>("/followups", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Follow-ups" subtitle="Patients scheduled to be seen again." />

      {followUps.loading && <LoadingState label="Loading follow-ups" />}
      {followUps.error && (
        <ErrorState message={followUps.error.message} onRetry={followUps.refetch} />
      )}
      {followUps.data?.items.length === 0 && <EmptyState title="No follow-ups scheduled" />}

      {followUps.data && followUps.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="Follow-ups">
            <thead>
              <tr>
                <Th>Due</Th>
                <Th>Status</Th>
                <Th>Instructions</Th>
              </tr>
            </thead>
            <tbody>
              {followUps.data.items.map((item) => (
                <tr key={item.id}>
                  <Td>
                    <span className="rs-numeric">{formatDate(item.due_date)}</span>
                  </Td>
                  <Td>{item.status}</Td>
                  <Td>{item.instructions || "—"}</Td>
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
export function DoctorAudit() {
  const activity = useQuery(
    (signal) => api.get<Page<AuditLogEntry>>("/audit/me", { page_size: 100 }, signal),
    [],
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="My activity"
        subtitle="A record of the actions carried out under your account."
      />

      {activity.loading && <LoadingState label="Loading activity" />}
      {activity.error && <ErrorState message={activity.error.message} onRetry={activity.refetch} />}
      {activity.data?.items.length === 0 && <EmptyState title="No recorded activity yet" />}

      {activity.data && activity.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="My activity">
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Action</Th>
                <Th>Resource</Th>
                <Th>Result</Th>
              </tr>
            </thead>
            <tbody>
              {activity.data.items.map((entry) => (
                <tr key={entry.id}>
                  <Td>{formatDateTime(entry.created_at)}</Td>
                  <Td>{entry.action.replace(/_/g, " ")}</Td>
                  <Td>{entry.resource_type?.replace(/_/g, " ") ?? "—"}</Td>
                  <Td>
                    <Badge tone={entry.result === "success" ? "ok" : "danger"}>
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
export function DoctorProfile() {
  const { user } = useAuth();

  return (
    <div className="flex max-w-xl flex-col gap-5">
      <PageHeader title="Profile" />
      <Panel className="flex flex-col gap-3">
        <ProfileRow label="Name" value={user?.full_name} />
        <ProfileRow label="Email" value={user?.email} />
        <ProfileRow label="Role" value="Doctor" />
        <ProfileRow label="Status" value={user?.status} />
      </Panel>
    </div>
  );
}
