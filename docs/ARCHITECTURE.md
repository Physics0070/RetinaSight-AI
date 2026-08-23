# Architecture

## Shape of the system

```
                    ┌──────────────────────────────┐
   Health worker    │   Flutter app (offline-first) │
   in the field  ───│   capture · quality · queue   │──┐
                    └──────────────────────────────┘  │
                                                       │  HTTPS
   Admin ┐                                             │  (JWT)
  Doctor ├─ React dashboard (4 role workspaces) ────────┤
 Patient ┘                                             │
                                                       ▼
                                    ┌────────────────────────────────┐
                                    │        FastAPI backend         │
                                    │  routers → services → repos    │
                                    └────────────────────────────────┘
                                       │            │            │
                              ┌────────┘            │            └────────┐
                              ▼                     ▼                     ▼
                       ┌────────────┐      ┌────────────────┐     ┌──────────────┐
                       │ PostgreSQL │      │ Object storage │     │  ML pipeline │
                       │  metadata  │      │ retinal images │     │  providers   │
                       └────────────┘      └────────────────┘     └──────────────┘
```

Images and metadata are deliberately separated: PostgreSQL holds records,
private object storage holds pixels, and the two are joined by an opaque
`storage_key` that is never exposed to a client.

## Backend layering

Strict, one-directional:

```
HTTP router      validation, authorization, response shaping
    ↓            (never contains a query or a business rule)
Service          business logic, workflow transitions, transactions
    ↓
Repository       all database access
    ↓
SQLAlchemy       models
```

A route handler never builds a query, and a repository never decides policy.
The rule is enforced by convention and visible in review: `grep` for `select(`
in `app/api/` returns only the handful of list endpoints that pass a prepared
statement straight to a repository's `paginate`.

### Why services own transactions

Repositories `flush` but never `commit`. The service that started a unit of work
commits it, so a multi-step clinical operation (capture → store → assess →
transition) either lands completely or not at all.

## The clinical workflow

One state machine, in one file
(`app/services/screening_state_machine.py`), owns every legal transition:

```
idle → patient_selected → capture_left/right_eye → quality_check
     → retake_required ⟲                    ↓
                              ready_for_inference → inference_running
     → result_available → explanation_available → referral_pending
     → referral_created → doctor_review → follow_up → completed
```

Two invariants are tested rather than assumed:

- **Every non-terminal state offers an exit** (`cancelled` or `completed`), so
  no user is ever trapped mid-workflow.
- **Terminal states are terminal** — a closed screening cannot be edited.

State lives on the `screening_sessions` row, never scattered across UI
components. A client that reloads, crashes, or switches device resumes from the
server's snapshot via `GET /screenings/{id}`.

## Configuration model

Three distinct tiers, deliberately not blurred:

| Tier | Lives in | Example | Changed by |
|---|---|---|---|
| Environment | `RS_*` env vars | database URL, bucket, secrets | deploy |
| Clinical/business rules | `system_configuration` table | risk rules, quality thresholds | admin, audited |
| Domain constants | `app/domain/enums.py` | the five DR grades, workflow states | code change |

Engines read tier 2 through `ConfigService`. A threshold literal in an engine is
a bug, and `scripts/check_no_hardcoding.py` fails the build on one.

## ML pipeline

`ModelProvider` is an interface; PyTorch, ONNX, the development placeholder and
an explicit "unavailable" provider all satisfy it. `ModelRegistry` decides which
one serves a request, preferring the database-registered ACTIVE model and
falling back to the environment.

The critical property: when a real model is configured but cannot be loaded, the
registry returns `UnavailableModelProvider`, whose `predict()` **raises**. The
system reports `MODEL NOT AVAILABLE` rather than silently degrading to
placeholder output that a clinician might act on.

See [ML_PIPELINE.md](ML_PIPELINE.md).

## Offline-first

The device — not the server — is the source of truth during a screening:

```
capture → on-device quality gate → encrypted local store → sync queue
        → (connectivity returns) → idempotent batch push → doctor dashboard
```

Idempotency comes from a client-generated `local_id`; the server treats
`(local_id, entity_type)` as unique. A retried batch updates rather than
duplicating a clinical record. See [OFFLINE_SYNC.md](OFFLINE_SYNC.md).

## Four separate frontends

Not one dashboard with conditional rendering. Each role gets its own route tree,
navigation, information hierarchy and visual material:

| Role | Route | Material | Optimised for |
|---|---|---|---|
| Health worker | `/user/*` | medical-device neumorphism | one-handed field use |
| Doctor | `/doctor/*` | dark clinical glass | judging retinal images |
| Patient | `/patient/*` | soft, calm, large type | low cognitive load |
| Admin | `/admin/*` | command-centre glass | dense monitoring |

The theme is driven by a `data-role` attribute on the document root, which
re-points the design tokens. See [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md).

## Authorization

Frontend route guards are **usability only**. Every request re-resolves the
caller's permissions from the database:

```
JWT → user id → roles → permissions → FastAPI dependency → handler
```

Permissions in the token are advisory for UI rendering and are never trusted.
A test proves it: demote a user and their already-issued token stops working on
the next request. See [RBAC.md](RBAC.md).

## Error handling

Services raise typed `AppError` subclasses. One handler converts them into a
client-safe envelope:

```json
{ "error": { "code": "permission_denied", "message": "You do not have permission…" } }
```

Stack traces and status codes go to logs, never to a user. The frontend renders
`error.message` directly, which is why no screen ever shows `AxiosError 500`.

## Deliberate exclusions

- **No Firebase.** Replaced by FastAPI + PostgreSQL + S3-compatible storage. A
  test scans the repository to keep it that way.
- **No fabricated metrics.** The API rejects a "validated" model that arrives
  without validation evidence.
- **No filesystem storage in production.** The service refuses to start,
  rather than losing patient images on the next deploy.
