/**
 * Configuration editor.
 *
 * This is where the clinical rules actually live: quality thresholds, risk
 * rules, referral routing. Editing here changes system behaviour immediately —
 * no redeploy, no duplicated copy of the rules in the frontend — and every
 * change is versioned and audited.
 */

import { useEffect, useState } from "react";

import { PageHeader } from "@/app/PageHeader";
import {
  Badge,
  Button,
  ErrorState,
  LoadingState,
  Panel,
} from "@/design-system/components/primitives";
import { api } from "@/lib/api";
import { useMutation, useQuery } from "@/lib/useApi";
import type { ConfigurationEntry } from "@/lib/types";

export function AdminConfiguration() {
  const entries = useQuery(
    (signal) => api.get<ConfigurationEntry[]>("/config", undefined, signal),
    [],
  );

  if (entries.loading) return <LoadingState label="Loading configuration" />;
  if (entries.error) {
    return <ErrorState message={entries.error.message} onRetry={entries.refetch} />;
  }

  const grouped = groupByCategory(entries.data ?? []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Configuration"
        subtitle="Clinical thresholds and rules. Changes take effect immediately and are audited."
      />

      <Panel
        className="flex items-start gap-3"
        style={{
          borderColor: "color-mix(in srgb, var(--rs-warn) 45%, transparent)",
          background: "color-mix(in srgb, var(--rs-warn) 8%, transparent)",
        }}
      >
        <span aria-hidden="true" style={{ color: "var(--rs-warn)" }}>
          ⚠
        </span>
        <p className="text-[var(--rs-text-sm)]">
          These values govern how screenings are graded and referred. They should
          be reviewed by a qualified clinician before being changed.
        </p>
      </Panel>

      {Object.entries(grouped).map(([category, items]) => (
        <section key={category} className="flex flex-col gap-3">
          <h2 className="text-[var(--rs-text-lg)] font-semibold">
            {category.replace(/_/g, " ")}
          </h2>
          {items.map((entry) => (
            <ConfigurationCard key={entry.id} entry={entry} onSaved={entries.refetch} />
          ))}
        </section>
      ))}
    </div>
  );
}

function ConfigurationCard({
  entry,
  onSaved,
}: {
  entry: ConfigurationEntry;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState(() => JSON.stringify(entry.value, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  // Re-sync when the server value changes (e.g. after a reset).
  useEffect(() => {
    setDraft(JSON.stringify(entry.value, null, 2));
    setDirty(false);
  }, [entry.value, entry.version]);

  const save = useMutation(async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch {
      setParseError("This is not valid JSON. Check for a missing comma or quote.");
      return;
    }
    setParseError(null);
    await api.put(`/config/${entry.key}`, { value: parsed });
    onSaved();
  });

  const reset = useMutation(async () => {
    await api.post(`/config/${entry.key}/reset`);
    onSaved();
  });

  return (
    <Panel className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rs-numeric font-semibold">{entry.key}</span>
            <Badge>v{entry.version}</Badge>
            {!entry.is_editable && <Badge tone="warn">Read only</Badge>}
          </div>
          <p className="max-w-2xl text-[var(--rs-text-sm)]" style={{ color: "var(--rs-ink-muted)" }}>
            {entry.description}
          </p>
        </div>
      </div>

      <label className="sr-only" htmlFor={`config-${entry.key}`}>
        Value for {entry.key}
      </label>
      <textarea
        id={`config-${entry.key}`}
        value={draft}
        readOnly={!entry.is_editable}
        spellCheck={false}
        onChange={(event) => {
          setDraft(event.target.value);
          setDirty(true);
        }}
        className="rs-numeric w-full rounded-[var(--rs-radius-md)] border p-3 text-[var(--rs-text-xs)]"
        style={{
          background: "var(--rs-surface-sunken)",
          borderColor: parseError ? "var(--rs-danger)" : "var(--rs-line)",
          color: "var(--rs-ink)",
          minHeight: "12rem",
          resize: "vertical",
        }}
      />

      {parseError && (
        <p role="alert" className="text-[var(--rs-text-sm)]" style={{ color: "var(--rs-danger)" }}>
          {parseError}
        </p>
      )}
      {save.error && <ErrorState message={save.error.message} />}

      {entry.is_editable && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            loading={save.loading}
            disabled={!dirty}
            onClick={() => void save.run()}
          >
            Save changes
          </Button>
          <Button variant="ghost" loading={reset.loading} onClick={() => void reset.run()}>
            Reset to default
          </Button>
          {dirty && (
            <span className="text-[var(--rs-text-xs)]" style={{ color: "var(--rs-warn)" }}>
              Unsaved changes
            </span>
          )}
        </div>
      )}
    </Panel>
  );
}

function groupByCategory(entries: ConfigurationEntry[]): Record<string, ConfigurationEntry[]> {
  return entries.reduce<Record<string, ConfigurationEntry[]>>((groups, entry) => {
    (groups[entry.category] ??= []).push(entry);
    return groups;
  }, {});
}
