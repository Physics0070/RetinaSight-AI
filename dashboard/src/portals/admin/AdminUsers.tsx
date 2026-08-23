/**
 * User administration.
 *
 * Search, filter, create, activate/deactivate and reassign roles. Every action
 * is re-authorised server-side and written to the audit log.
 */

import { useState, type FormEvent } from "react";

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
  Table,
  Td,
  Th,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMutation, useQuery } from "@/lib/useApi";
import type { Page, RoleName, UserDetail } from "@/lib/types";
import { formatDateTime } from "@/portals/worker/WorkerDashboard";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  health_worker: "Health worker",
  doctor: "Doctor",
  patient: "Patient",
};

export function AdminUsers({ roleFilter }: { roleFilter?: RoleName }) {
  const { user: currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<string>(roleFilter ?? "");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);

  const users = useQuery(
    (signal) =>
      api.get<Page<UserDetail>>(
        "/users",
        {
          query: query || undefined,
          role: role || undefined,
          status: status || undefined,
          page_size: 100,
        },
        signal,
      ),
    [query, role, status],
  );

  const setUserStatus = useMutation(async (userId: string, next: string) => {
    await api.post(`/users/${userId}/status`, { status: next });
    users.refetch();
  });

  const changeRole = useMutation(async (userId: string, next: string) => {
    await api.post(`/users/${userId}/role`, { role: next });
    users.refetch();
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={roleFilter ? `${ROLE_LABELS[roleFilter]}s` : "Users"}
        subtitle="Accounts, roles and access."
        actions={
          <Button variant="primary" onClick={() => setCreating((v) => !v)}>
            {creating ? "Close" : "Create user"}
          </Button>
        }
      />

      {creating && (
        <CreateUserForm
          onCreated={() => {
            setCreating(false);
            users.refetch();
          }}
        />
      )}

      <Panel className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <form
          className="contents"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            setQuery(search.trim());
          }}
        >
          <Field label="Search" htmlFor="user-search">
            <Input
              id="user-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Name or email"
            />
          </Field>
          <Field label="Role" htmlFor="role-filter">
            <Select
              id="role-filter"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={Boolean(roleFilter)}
            >
              <option value="">All roles</option>
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Status" htmlFor="status-filter">
            <Select id="status-filter" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="suspended">Suspended</option>
            </Select>
          </Field>
          <div className="flex items-end">
            <Button type="submit">Apply</Button>
          </div>
        </form>
      </Panel>

      {users.loading && <LoadingState label="Loading users" />}
      {users.error && (
        <ErrorState message={users.error.message} onRetry={users.refetch} />
      )}
      {users.data?.items.length === 0 && <EmptyState title="No users match these filters" />}

      {users.data && users.data.items.length > 0 && (
        <Panel padded={false}>
          <Table caption="User accounts">
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Email</Th>
                <Th>Role</Th>
                <Th>Organisation</Th>
                <Th>Status</Th>
                <Th>Last active</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((user) => {
                const isSelf = user.id === currentUser?.id;
                return (
                  <tr key={user.id}>
                    <Td>
                      <span className="font-semibold">{user.full_name}</span>
                    </Td>
                    <Td>{user.email}</Td>
                    <Td>
                      <Select
                        aria-label={`Role for ${user.full_name}`}
                        value={user.roles[0] ?? ""}
                        disabled={isSelf || changeRole.loading}
                        onChange={(e) => void changeRole.run(user.id, e.target.value)}
                      >
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </Select>
                    </Td>
                    <Td>{user.clinic_name ?? "—"}</Td>
                    <Td>
                      <Badge tone={user.status === "active" ? "ok" : "warn"}>
                        {user.status}
                      </Badge>
                    </Td>
                    <Td>{formatDateTime(user.last_active_at)}</Td>
                    <Td>
                      <Button
                        size="sm"
                        disabled={isSelf}
                        loading={setUserStatus.loading}
                        onClick={() =>
                          void setUserStatus.run(
                            user.id,
                            user.status === "active" ? "inactive" : "active",
                          )
                        }
                        title={
                          isSelf ? "You cannot change your own account status." : undefined
                        }
                      >
                        {user.status === "active" ? "Deactivate" : "Activate"}
                      </Button>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Panel>
      )}

      {(setUserStatus.error || changeRole.error) && (
        <ErrorState
          message={(setUserStatus.error ?? changeRole.error)!.message}
        />
      )}
    </div>
  );
}

function CreateUserForm({ onCreated }: { onCreated: () => void }) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<RoleName>("health_worker");

  const create = useMutation(async () => {
    await api.post("/users", {
      email: email.trim(),
      full_name: fullName.trim(),
      password,
      role,
    });
    setEmail("");
    setFullName("");
    setPassword("");
    onCreated();
  });

  return (
    <Panel className="flex flex-col gap-4">
      <h2 className="rs-label">Create a user</h2>
      <form
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
          void create.run();
        }}
      >
        <Field label="Full name" htmlFor="new-name" required>
          <Input
            id="new-name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        </Field>
        <Field label="Email" htmlFor="new-email" required>
          <Input
            id="new-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field
          label="Temporary password"
          htmlFor="new-password"
          hint="The user should change this after signing in."
          required
        >
          <Input
            id="new-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </Field>
        <Field label="Role" htmlFor="new-role" required>
          <Select
            id="new-role"
            value={role}
            onChange={(e) => setRole(e.target.value as RoleName)}
          >
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>

        <div className="sm:col-span-2 xl:col-span-4">
          {create.error && <ErrorState message={create.error.message} />}
        </div>

        <div className="flex items-end">
          <Button type="submit" variant="primary" loading={create.loading}>
            Create user
          </Button>
        </div>
      </form>
    </Panel>
  );
}
