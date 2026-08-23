# Testing

```
Backend    150 passing
Frontend    87 passing
ML          35 passing
Mobile      26 passing
Scanner    211 files, clean (5 narrow exemptions)
```

```bash
cd backend    && python -m pytest          # 150
cd dashboard  && npm test                  # 87
cd ml         && python -m pytest tests/   # 35
cd mobile     && flutter test              # 26
python scripts/check_no_hardcoding.py --verbose
```

---

## What is actually being tested

The suite is written around **behaviour that would be dangerous if wrong**,
rather than around coverage percentage.

### Backend — `backend/tests/`

| File | Tests | Focus |
|---|---|---|
| `test_auth.py` | 12 | login, rotation, replay defence, enumeration |
| `test_rbac.py` | 17 | permission matrix, patient isolation, audit on denial |
| `test_storage.py` | 24 | signed-URL security, traversal, idempotent upload |
| `test_ml_pipeline.py` | 21 | preprocessing, quality gate, provider honesty, Grad-CAM |
| `test_engines.py` | 26 | risk rules, referral routing, configuration service |
| `test_workflow.py` | 20 | state machine, consent gate, end-to-end flow |
| `test_no_hardcoding.py` | 5 | hardcoding, secrets, Firebase, `.env` hygiene |

Each test runs against an **isolated in-memory SQLite database with the real
RBAC policy seeded**. Authorization is exercised for real — never mocked.

### Frontend — `dashboard/src/test/`

| File | Tests | Focus |
|---|---|---|
| `risk.test.tsx` | 17 | severity never colour-only, clinical framing, patient language |
| `auth.test.tsx` | 10 | role resolution, route guards, offline error classification |
| `workflow.test.tsx` | 17 | capture feedback, offline UX, image viewer, a11y |

### ML training — `ml/tests/`

| File | Tests | Focus |
|---|---|---|
| `test_metrics.py` | 12 | kappa ordinality, macro-F1 vs accuracy, referable-DR sensitivity |
| `test_dataset.py` | 13 | manifest/folder discovery, stratified split, class weighting, **train/serve preprocessing identity** |

Two of these encode lessons that are easy to get wrong:

```python
test_accuracy_alone_would_hide_a_useless_model
```
A model predicting "no DR" for everything scores 90% accuracy on a realistically
skewed set. The test asserts macro-F1 exposes it (< 0.30) and referable-DR
sensitivity is 0.0.

```python
test_preprocessing_matches_inference
```
Asserts the training pipeline uses the *same function objects* as the serving
code — not a copy. Train/serve skew would silently degrade a deployed model with
no error anywhere.

### Mobile — `mobile/test/`

| File | Focus |
|---|---|
| `quality_gate_test.dart` | on-device gate against synthetic fundus images |
| `screening_workflow_test.dart` | state machine parity with the backend |

---

## The tests that matter most

These encode clinical and security invariants. If one fails, something
genuinely unsafe has changed.

**Permissions are not read from the token**
```python
test_permission_check_is_not_taken_from_the_token
```
Demote a user mid-session; their existing token stops working on the next
request. This is the difference between real authorization and decoration.

**A patient cannot reach another patient's record**
```python
test_patient_cannot_access_another_patients_record
test_cross_patient_attempt_is_audited
```
Denied *and* written to the audit log with the target id.

**Administration is not clinical authority**
```python
test_administration_and_clinical_duties_are_separated
```
No admin holds `CLINICAL_REVIEW`; no doctor holds `CONFIG_MANAGE`.

**A rejected image never reaches the model**
```python
test_inference_is_blocked_until_quality_passes
```

**No state traps the user**
```python
test_every_open_state_offers_an_exit
```
Iterates the whole transition table asserting every non-terminal state can reach
`cancelled` or `completed`.

**Retries cannot duplicate clinical records**
```python
test_identical_bytes_are_stored_once
test_repeated_start_with_same_local_id_is_idempotent
```

**A placeholder model is never presented as real**
```python
test_development_model_results_are_flagged
test_unavailable_provider_refuses_rather_than_inventing_output
test_provider_description_reports_no_invented_metrics
```

**Clinical rules are configuration, not code**
```python
test_risk_rules_are_configuration_driven
test_thresholds_are_configuration_driven
```
Change the configuration, the verdict changes. Proves no threshold is baked in.

**Signed URLs cannot be forged or extended**
```python
test_expired_signature_is_rejected
test_tampered_signature_is_rejected
test_signature_for_extended_expiry_is_rejected
```

**Severity is never colour-only**
```ts
"badge for %s carries a text label"
"badge for %s carries a distinct glyph"
"uses a different glyph for every level"
```

---

## End-to-end

`test_full_screening_to_follow_up_flow` walks the complete clinical path:

```
patient → consent → capture both eyes → quality gate → AI inference
        → Grad-CAM → risk → referral → clinician review → follow-up → completed
```

asserting the reviewer is recorded, agreement with the AI is derived, and the
session reaches a terminal state.

---

## The hardcoding scanner

`scripts/check_no_hardcoding.py` runs as part of the backend suite, so a
regression fails the build rather than waiting for review. Ten rules cover
Firebase, hardcoded URLs, API keys, passwords, AWS keys, private keys, database
DSNs, clinical thresholds and referral literals.

### Exemptions are per-rule, never per-file

This was previously a list of nine paths, each excused from **every** rule. That
is a hole rather than a policy: an allowlisted file could have carried an AWS
key, a private key or a Firebase import and the scan would still have printed
`PASS`. Four of the nine turned out to suppress rules that never fired at all.

Each entry now names only the rules it needs. Every other rule still applies to
that path:

| Path | Exempt from | Why |
|---|---|---|
| `scripts/check_no_hardcoding.py` | `firebase` | the scanner must contain the patterns it searches for |
| `.env.example`, `dashboard/.env.example` | `localhost_url` | they *are* the development defaults; production never reads them |
| `backend/tests/test_no_hardcoding.py` | `firebase` | the test asserting Firebase is absent must name it to search for it |
| `backend/tests/test_config_paths.py` | `postgres_dsn` | a fabricated DSN, asserting non-SQLite URLs pass through unchanged |

The last two are exempted **per file** rather than by weakening the whole
`tests/` directory — a genuine Firebase import or a real DSN in any other test
is still a failure.

Directory exemptions are narrowed the same way. Test fixtures legitimately hold
throwaway passwords, loopback URLs and threshold literals; nothing legitimately
holds a cloud key or a private key, so those rules keep applying inside `tests/`.

`.env` files are now scanned too. They carry no scannable suffix, and they are
exactly where a real secret gets pasted by accident.

Three tests hold the line: exemptions must be a **strict subset** of the rules,
`.env` files must actually be reached, and a credential planted inside `tests/`
must still be caught — it is, and it would not have been before.

Anything else containing a URL, secret or threshold literal fails.

---

## Writing a new test

Follow the existing shape:

1. **Name the behaviour, not the function.**
   `test_patient_cannot_access_another_patients_record`, not `test_authorize`.
2. **Use the real policy.** `db_session` seeds the actual RBAC matrix; don't mock it.
3. **Assert the negative too.** For any new permission, assert which roles must
   *not* have it.
4. **Prefer end-to-end for clinical paths.** A workflow bug usually lives
   between two correct units.

---

## Known gaps

Stated rather than glossed over:

- **The Flutter tests have never been executed.** They were written against the
  documented Dart APIs but no SDK was available. Run
  `flutter analyze && flutter test` before trusting the mobile layer.
- **No load or performance testing.**
- **No browser-level end-to-end** (Playwright/Cypress) — the frontend is tested
  at component level with a mocked API.
- **The real ONNX/PyTorch providers are untested against actual weights**; only
  their unavailable-path behaviour is covered.
- **PostgreSQL-specific behaviour is untested** — the suite runs on SQLite.
  Migrations have been verified to apply and reverse, but running the suite
  against PostgreSQL before production is advisable.
