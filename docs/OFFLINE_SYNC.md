# Offline-first and synchronisation

Offline is a **normal operating mode**, not an error path. A health worker at a
rural PHC completes an entire screening — registration, consent, capture,
quality gating, queueing — with no connectivity at all.

```
capture → on-device quality gate → encrypted local store → sync queue
        → (connectivity returns) → idempotent batch push → doctor dashboard
```

---

## The device is the source of truth during a screening

Everything is written locally **first**, then queued. Nothing in the workflow
waits on a network round trip:

| Step | Local | Network |
|---|---|---|
| Register patient | write + enqueue | later |
| Record consent | write | later |
| Capture image | write to private storage | later |
| Quality gate | **runs on device** | re-verified on upload |
| Retake decision | immediate | — |
| Screening result | — | requires sync |

The one thing that genuinely needs the server is the AI result. The device
queues the screening and the server produces it — the app does **not** show
placeholder output as a screening result.

---

## Encrypted local storage

`mobile/lib/data/local_store.dart`

- Structured records live in a **SQLCipher-encrypted** SQLite database.
- The key is generated on first run and stored in the platform
  keystore/keychain via `flutter_secure_storage` — never in the database, never
  in shared preferences, never in source.
- Captured images are written to the app's private directory, outside any
  world-readable location.

Losing the key makes the local database unreadable. That is the intended
behaviour if a device is wiped or stolen.

---

## Idempotency — the core guarantee

> **Retries must never duplicate a clinical record.**

Every queued item carries a client-generated `local_id`. The server enforces
`UNIQUE (local_id, entity_type)`, so replaying a batch after a dropped
connection **updates** rather than inserting a second record.

Three independent layers of protection:

1. **Sync queue** — replaying an item already marked `synced` returns
   `status: "duplicate"` and applies nothing.
2. **Session start** — `start_screening(local_id=...)` returns the existing
   session instead of creating another
   (`test_repeated_start_with_same_local_id_is_idempotent`).
3. **Image upload** — deduplicated by SHA-256 content hash *and* by `local_id`,
   so identical bytes are stored once
   (`test_identical_bytes_are_stored_once`).

Inference is idempotent too: re-running a screening returns the stored result
unless explicitly forced.

---

## Queue states

```
PENDING ──► UPLOADING ──► SYNCED
   ▲            │
   │            ▼
RETRYING ◄── FAILED
```

| State | Meaning |
|---|---|
| `pending` | queued, not yet attempted |
| `uploading` | in flight |
| `synced` | confirmed stored server-side |
| `failed` | rejected; carries a reason |
| `retrying` | connection lost mid-flight; will resume |

Each row records `attempt_count`, `last_attempt_at`, `last_error` and the
returned `server_id`.

---

## Ordering

Items are pushed **patient → session → image**, because each depends on the
server id of the one before it. The sync service sorts the batch accordingly
rather than relying on insertion order.

---

## Failure isolation

One bad item never blocks the queue. Each is processed independently:

- A **rejected** item is parked with its reason after
  `maxSyncAttempts` (default 5) and reported in the UI. It is not retried
  forever.
- A **lost connection** mid-drain marks the current item `retrying` and stops
  the batch cleanly; the rest resume on reconnect.
- Image bytes are read from disk **at send time**, so the queue table stays
  small and the file remains the single copy.

---

## Triggers

The sync service drains the queue when:

1. **connectivity is restored** — the moment that matters most, handled by a
   `connectivity_plus` listener;
2. **on a timer** (`AppConfig.syncInterval`, default 30s) while online;
3. **manually**, via *Sync now*.

Overlapping calls are a no-op rather than a double-send.

---

## Offline UX

Never a bare `Network Error`. Both the app and the dashboard say what is
happening and what will happen next:

```
OFFLINE MODE

RetinaSight AI is continuing offline. Your screening data is stored
securely on this device and will synchronise when connectivity returns.

3 items waiting to sync.
```

The API client distinguishes "no connection" (`network_unavailable`) from
"the server rejected this", so the UI can respond appropriately instead of
showing one generic failure. Asserted in the frontend tests.

---

## Server side

`POST /api/v1/sync/push`

```json
{
  "device_id": "device-abc123",
  "items": [
    {
      "local_id": "patient-1730000000",
      "entity_type": "patient",
      "operation": "create",
      "payload": { "full_name": "…", "consents": { "screening": true } }
    }
  ]
}
```

Response reports each item independently:

```json
{
  "accepted": 2,
  "duplicates": 1,
  "failed": 0,
  "items": [
    { "local_id": "patient-1730000000", "status": "synced", "server_id": "…" },
    { "local_id": "session-1730000001", "status": "duplicate", "server_id": "…" }
  ]
}
```

Sync deliberately **reuses the same services** as online requests, so consent
checks, validation and audit logging are identical whether a record arrived
live or from a queue. There is no privileged back door for synced data.

---

## Conflict handling

The current model is **last-write-wins on the server**, which is safe here
because the data is append-only in practice: a screening belongs to one device
and one worker, and clinical records are added rather than concurrently edited.
Referrals and reviews are created server-side.

If multi-device editing of the same patient record is introduced later, this
becomes insufficient and will need per-field versioning.

---

## Monitoring

- Health worker: **Sync** page — counts by state, per-item detail, failure
  reasons.
- Admin: dashboard shows platform-wide pending and failed counts.
- `GET /sync/status?device_id=…` returns counts for one device.
