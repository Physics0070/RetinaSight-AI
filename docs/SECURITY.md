# Security

This system handles patient identifiers, retinal photographs and clinical
decisions. The controls below are implemented and tested, not aspirational.

---

## Authentication

**Passwords** — Argon2id via `argon2-cffi`. Plaintext is never stored, never
logged and never returned. Hashes are transparently upgraded on login when the
Argon2 parameters change.

**Tokens** — short-lived access JWT + longer-lived refresh JWT, signed with
**two independent secrets** so rotating one does not invalidate the other.

### Refresh-token rotation with replay detection

Every refresh issues a new token and marks the presented one revoked, recording
`replaced_by_jti`. If an **already-rotated token is presented again**, that is
treated as evidence of theft rather than a retry:

```
presented token revoked?  →  revoke the entire token family for that user
                          →  audit the event
                          →  reject
```

Both the rotation and the family revocation are covered by tests
(`test_refresh_rotates_token_and_old_token_stops_working`,
`test_refresh_replay_revokes_the_whole_token_family`).

### Account enumeration

A wrong password and a non-existent account return a **byte-identical**
response. Asserted in `test_login_rejects_wrong_password_without_revealing_account`.

### Deactivation

Setting a user inactive revokes all their refresh tokens immediately; the next
request with a live access token also fails, because status is re-checked per
request.

---

## Authorization

Full detail in [RBAC.md](RBAC.md). The security-relevant properties:

1. **Permissions are re-resolved from the database on every request.** The token
   carries a permission list purely as a UI hint and is never trusted for
   enforcement.
2. **Frontend guards are not security.** They exist so users do not see dead
   ends. Every endpoint declares its own required permission.
3. **Patient isolation is explicit.** `authorize_patient()` grants staff access
   by permission and a patient access only to their own record. Anything else is
   denied *and audited*.
4. **Duties are separated.** Platform administrators do not hold
   `CLINICAL_REVIEW`. No admin can sign off a clinical case.

---

## Retinal images

Images are the most sensitive artefact in the system.

- Stored in **private** object storage — never in the database, never on a
  public path, never with a public-read ACL.
- Reached only through **short-lived signed URLs** (default 300s, configurable).
- The `storage_key` is **absent from every API schema**; clients receive URLs,
  never paths. Asserted in `test_storage_key_is_never_exposed_in_the_api_schema`.
- Keys are opaque and non-enumerable — UUID segments only, never a patient name.

### Signed-URL integrity (local provider)

The development provider mirrors the S3 presigned model with HMAC-SHA256 over
`key:expiry`, verified in constant time. Tests cover the attacks that matter:

| Attempt | Result |
|---|---|
| Expired signature | rejected |
| Tampered signature | rejected |
| Signature minted for a *different* object | rejected |
| Client extends its own expiry | rejected |

### Path traversal

Storage keys are validated against a strict pattern, and the resolved filesystem
path must remain inside the storage root. `../../../etc/passwd`, absolute paths
and embedded `..` are all rejected.

### Upload validation

Client-supplied `Content-Type` is **not trusted**. Uploaded bytes are decoded to
confirm they are a real image before anything is stored, so a shell script
cannot be persisted as `image/jpeg`. Size and permitted formats are
configuration-driven.

---

## Secrets

- No credential, key or connection string is committed. Enforced by
  `scripts/check_no_hardcoding.py` and by `test_no_env_file_is_committed`.
- `.env.example` documents every variable with placeholders only. A test asserts
  every `RS_*` setting is documented.
- Development defaults are **deliberately obvious** (`dev-only-insecure-…`) and
  a test asserts they remain recognisable, so an unset production secret is
  loud rather than subtle.

Generate real values with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Three separate secrets are required: `RS_JWT_SECRET`,
`RS_JWT_REFRESH_SECRET`, `RS_STORAGE_SIGNING_SECRET`.

---

## Logging and audit

**Never logged:** passwords, password hashes, tokens, authorization headers,
raw patient data, image bytes. A logging filter redacts these keys even if a
caller passes them in `extra`.

**Audit log** records actor, action, resource, result, IP and timestamp for
security- and clinically-significant events — including denials. The audit
service sanitises its context payload, dropping forbidden keys and anything
non-serialisable, so patient data cannot leak into it by accident.

Clinical notes are deliberately **excluded** from audit context: the fact a
review happened is auditable, its content is patient data.

---

## Transport and CORS

- HTTPS is assumed in production and terminated at the platform edge;
  `X-Forwarded-For` is honoured for client IP attribution.
- CORS origins are an explicit allowlist from `RS_CORS_ORIGINS` — never `*`.
- API docs (`/docs`, `/openapi.json`) are **disabled in production**.

---

## Mobile

- Structured records live in a **SQLCipher-encrypted** SQLite database.
- The encryption key is generated on first run and held in the platform
  keystore/keychain via `flutter_secure_storage` — never in the database, never
  in shared preferences, never in source.
- Captured images are written to the app's private directory.
- Tokens are stored in secure storage, not preferences.

---

## Known gaps

Stated plainly rather than implied to be handled:

- **Rate limiting is configured but not enforced.**
  `RS_LOGIN_RATE_LIMIT_PER_MINUTE` exists; enforcement belongs at the edge
  (reverse proxy / platform WAF) and is not implemented in-process.
- **No MFA.** Single-factor authentication only.
- **No field-level encryption at rest** in PostgreSQL beyond what the platform
  provides. Patient names are stored in plaintext columns.
- **Signed image URLs are bearer credentials** for their lifetime. Anyone with
  the URL can fetch the image until it expires; the short TTL is the mitigation.
- **The Flutter app is unverified** — it has not been compiled or run.
- **No penetration test** has been performed.

---

## Reporting

Security issues should be reported privately to the maintainers rather than
through a public issue.
