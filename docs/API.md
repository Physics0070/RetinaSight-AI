# API reference

Base path: `/api/v1` (configurable via `RS_API_PREFIX`).
Interactive docs at `/docs` — **disabled in production**.

---

## Conventions

**Authentication** — `Authorization: Bearer <access_token>` on everything except
`/auth/login` and `/auth/refresh`.

**Errors** — one client-safe envelope. Stack traces and status codes stay in
logs; the `message` is written to be shown to a user as-is.

```json
{
  "error": {
    "code": "permission_denied",
    "message": "You do not have permission to perform this action.",
    "details": null
  }
}
```

| Code | HTTP | Meaning |
|---|---|---|
| `authentication_failed` | 401 | wrong credentials |
| `invalid_token` | 401 | expired, malformed or revoked token |
| `account_inactive` | 403 | account not active |
| `permission_denied` | 403 | authenticated but not authorised |
| `not_found` | 404 | no such record |
| `conflict` | 409 | already exists |
| `invalid_workflow_transition` | 409 | action not available at this step |
| `validation_error` | 422 | invalid input (field detail in `details`) |
| `model_not_available` | 503 | no usable screening model |
| `storage_unavailable` | 503 | object storage unreachable |

**Pagination** — list endpoints take `page` and `page_size` and return:

```json
{ "items": [], "total": 0, "page": 1, "page_size": 25, "pages": 0 }
```

---

## Authentication — `/auth`

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/auth/login` | — | returns tokens + identity |
| POST | `/auth/refresh` | — | **rotates** the refresh token |
| POST | `/auth/logout` | authenticated | revokes one or all sessions |
| GET | `/auth/me` | authenticated | identity, roles, effective permissions |
| POST | `/auth/change-password` | authenticated | revokes other sessions |

```http
POST /api/v1/auth/login
{ "email": "user@example.com", "password": "…" }
```

```json
{
  "tokens": { "access_token": "…", "refresh_token": "…", "token_type": "bearer", "expires_in": 900 },
  "user": { "id": "…", "roles": ["doctor"], "permissions": ["CLINICAL_REVIEW", "…"] }
}
```

> `permissions` is a **UI hint only**. The backend re-resolves permissions from
> the database on every request and never trusts the token's copy.

Presenting an already-rotated refresh token revokes the entire token family for
that user — see [SECURITY.md](SECURITY.md).

---

## Users — `/users`  *(requires `USER_MANAGE`)*

| Method | Path | Notes |
|---|---|---|
| GET | `/users` | search, filter by role/status, sort |
| POST | `/users` | creates the staff profile too |
| GET | `/users/{id}` | |
| PATCH | `/users/{id}` | |
| POST | `/users/{id}/status` | deactivation revokes all sessions |
| POST | `/users/{id}/role` | audited; cannot change your own |

---

## Patients — `/patients`

| Method | Path | Permission |
|---|---|---|
| GET | `/patients/me` | `PATIENT_VIEW_SELF` |
| GET | `/patients/me/consents` | `PATIENT_VIEW_SELF` |
| GET | `/patients` | `PATIENT_VIEW` |
| POST | `/patients` | `PATIENT_CREATE` |
| GET | `/patients/{id}` | ownership-checked |
| PATCH | `/patients/{id}` | `PATIENT_UPDATE` |
| GET/POST | `/patients/{id}/consents` | ownership-checked |

Every `{patient_id}` route passes through `authorize_patient()`: staff by
permission, a patient only to their own record, everything else denied **and
audited**.

---

## Screenings — `/screenings`

The workflow API. Transitions are validated against the state machine; an
out-of-order call returns `invalid_workflow_transition` rather than corrupting
the record.

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/screenings` | `SCREENING_CREATE` | **requires recorded consent** |
| GET | `/screenings` | `SCREENING_VIEW` | |
| GET | `/screenings/{id}` | `SCREENING_VIEW` | full resumable snapshot |
| POST | `/screenings/{id}/capture` | `SCREENING_CREATE` | multipart; runs the quality gate |
| POST | `/screenings/{id}/retake` | `SCREENING_CREATE` | |
| POST | `/screenings/{id}/ready` | `SCREENING_CREATE` | proceed with one eye |
| GET | `/screenings/{id}/quality` | `SCREENING_VIEW` | |
| POST | `/screenings/{id}/inference` | `INFERENCE_RUN` | idempotent unless `?force=true` |
| GET | `/screenings/{id}/results` | `SCREENING_VIEW` | |
| GET | `/screenings/{id}/explanations` | `SCREENING_VIEW` | Grad-CAM + signed URLs |
| GET | `/screenings/{id}/risk` | `SCREENING_VIEW` | |
| POST | `/screenings/{id}/referral` | `REFERRAL_CREATE` | |
| POST | `/screenings/{id}/submit-review` | `SCREENING_CREATE` | |
| POST | `/screenings/{id}/complete` | `SCREENING_CREATE` | |
| POST | `/screenings/{id}/cancel` | `SCREENING_CREATE` | always available while open |
| POST | `/screenings/{id}/save-exit` | `SCREENING_CREATE` | leaves it resumable |

### Capture

```http
POST /api/v1/screenings/{id}/capture
Content-Type: multipart/form-data

file=<image>  eye_side=left  local_id=device-capture-001  captured_offline=false
```

```json
{
  "image": { "id": "…", "eye_side": "left", "capture_index": 0 },
  "quality": {
    "is_acceptable": false,
    "overall_score": 0.34,
    "blur_score": 0.21,
    "issues": ["blur"],
    "recommendations": ["Hold the phone steady and let the camera focus."]
  },
  "retake_required": true,
  "session_state": "retake_required"
}
```

A rejected image **never reaches the model**. Calling `/inference` on a
quality-blocked session returns `invalid_workflow_transition`.

### Inference

```json
{
  "results": [ { "category": "moderate", "confidence": 0.71, "is_development_model": true } ],
  "worst": { "…": "…" },
  "risk": { "risk_level": "moderate", "requires_clinician_review": true },
  "model_status": { "is_development_model": true, "clinically_validated": false },
  "disclaimer": "AI-assisted screening support. This is not a diagnosis…"
}
```

`disclaimer` and `is_development_model` are always present and must be surfaced.

---

## Images — `/images`

| Method | Path | Permission |
|---|---|---|
| POST | `/images` | `IMAGE_UPLOAD` |
| GET | `/images/session/{id}` | `IMAGE_VIEW` |
| GET | `/images/{id}` | `IMAGE_VIEW` |
| GET | `/images/blob` | signed URL only |

Responses carry a short-lived `url`, never a `storage_key`. `/images/blob`
authenticates by HMAC signature and expiry (the S3 presigned-URL model) and is
declared before `/{image_id}` so the literal path is not swallowed by the
parameter.

---

## Clinical — reviews, referrals, follow-ups

| Method | Path | Permission |
|---|---|---|
| GET | `/reviews/queue` | `CLINICAL_REVIEW` |
| GET | `/reviews/{id}` | `CLINICAL_REVIEW` |
| POST | `/reviews/{id}/claim` | `CLINICAL_REVIEW` |
| POST | `/reviews/{id}/release` | `CLINICAL_REVIEW` |
| POST | `/reviews/{id}/complete` | `CLINICAL_REVIEW` |
| GET | `/referrals`, `/referrals/{id}` | `REFERRAL_VIEW` |
| GET | `/followups` | authenticated (patients scoped to self) |
| POST | `/followups` | `FOLLOWUP_MANAGE` |
| POST | `/followups/{id}/complete`, `/cancel` | `FOLLOWUP_MANAGE` |

The queue is ordered by the configured risk engine — urgent first, then oldest
within a band.

```http
POST /api/v1/reviews/{id}/complete
{
  "decision": "confirm_ai",
  "clinician_category": "moderate",
  "notes": "Reviewed against the retinal images and heatmap.",
  "follow_up_due": "2026-05-01"
}
```

`agrees_with_ai` is derived by comparing the clinician's grading with the AI
result, so model/clinician agreement can be tracked over time.

---

## Sync — `/sync`  *(requires `SYNC_WRITE`)*

| Method | Path | Notes |
|---|---|---|
| POST | `/sync/push` | idempotent batch |
| GET | `/sync/status` | counts by state |
| GET | `/sync/queue` | item detail |

See [OFFLINE_SYNC.md](OFFLINE_SYNC.md).

---

## Administration

| Method | Path | Permission |
|---|---|---|
| GET | `/admin/dashboard` | `SYSTEM_VIEW` |
| GET | `/admin/system-health` | `SYSTEM_VIEW` |
| GET | `/clinics` | authenticated |
| POST | `/clinics` | `CLINIC_MANAGE` |
| GET | `/models`, `/models/status` | `MODEL_MANAGE` (status: any) |
| POST | `/models` | `MODEL_MANAGE` |
| POST | `/models/{id}/status` | `MODEL_MANAGE` |
| POST | `/models/{id}/validation` | `MODEL_MANAGE` |
| GET/PUT | `/config`, `/config/{key}` | `CONFIG_MANAGE` |
| POST | `/config/{key}/reset` | `CONFIG_MANAGE` |
| GET/PUT | `/config-flags` | `CONFIG_MANAGE` |
| GET | `/audit` | `AUDIT_VIEW` |
| GET | `/audit/me` | authenticated |

Every dashboard figure is a database count. An empty system reports zeros.

`POST /models/{id}/validation` **rejects** `validation_status: "validated"` when
`validation_metrics` is empty — a validation claim requires evidence.

---

## Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/health/ready` | readiness, includes a real database round-trip |

These sit outside `/api/v1` and need no authentication.
