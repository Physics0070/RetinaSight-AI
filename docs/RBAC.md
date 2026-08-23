# Roles and permissions

## The enforcement model

```
JWT → user id → roles (DB) → permissions (DB) → FastAPI dependency → handler
```

Two properties matter more than the permission list itself:

**1. Permissions are re-resolved from the database on every request.**
The token carries a permission array, but it is used *only* to render the UI.
Enforcement never reads it. A test proves the difference: demote an
administrator and their already-issued, still-unexpired token stops working on
the very next request (`test_permission_check_is_not_taken_from_the_token`).

**2. Frontend route guards are not security.**
`RequireRole` exists so a user is not shown a dead end. Bypassing it in the
browser yields an empty screen and a 403 from the API, because every endpoint
declares its own requirement:

```python
CanReview = Annotated[Access, Depends(require_permission(Permission.CLINICAL_REVIEW))]
```

---

## Roles

| Role | Workspace | Purpose |
|---|---|---|
| `admin` | `/admin/*` | Platform administration, configuration, oversight |
| `health_worker` | `/user/*` | Field screening: registration, capture, referral |
| `doctor` | `/doctor/*` | Clinical review of screenings and referrals |
| `patient` | `/patient/*` | Access to one's own results and follow-ups |

---

## Permission matrix

| Permission | Admin | Health worker | Doctor | Patient |
|---|:--:|:--:|:--:|:--:|
| `PATIENT_VIEW_SELF` | | | | ✅ |
| `PATIENT_VIEW` | ✅ | ✅ | ✅ | |
| `PATIENT_CREATE` | | ✅ | | |
| `PATIENT_UPDATE` | | ✅ | | |
| `SCREENING_CREATE` | | ✅ | | |
| `SCREENING_VIEW` | ✅ | ✅ | ✅ | |
| `IMAGE_UPLOAD` | | ✅ | | |
| `IMAGE_VIEW` | | ✅ | ✅ | |
| `INFERENCE_RUN` | | ✅ | | |
| `EXPLANATION_VIEW` | | ✅ | ✅ | |
| `RISK_VIEW` | ✅ | ✅ | ✅ | |
| `REFERRAL_CREATE` | | ✅ | ✅ | |
| `REFERRAL_VIEW` | ✅ | ✅ | ✅ | |
| **`CLINICAL_REVIEW`** | ❌ | ❌ | ✅ | ❌ |
| `FOLLOWUP_MANAGE` | | ✅ | ✅ | |
| `SYNC_WRITE` | | ✅ | | |
| `USER_MANAGE` | ✅ | | | |
| `CLINIC_MANAGE` | ✅ | | | |
| `MODEL_MANAGE` | ✅ | | | |
| `CONFIG_MANAGE` | ✅ | | | |
| `AUDIT_VIEW` | ✅ | | | |
| `SYSTEM_VIEW` | ✅ | | | |

### Why admin does not hold `CLINICAL_REVIEW`

Administration and clinical authority are separated on purpose. A platform
administrator can manage accounts, clinics, models and configuration — but
**cannot sign off a clinical case**. Only a doctor can. This is asserted in
`test_administration_and_clinical_duties_are_separated`.

The inverse also holds: a doctor cannot change system configuration, so
clinical rules cannot be quietly altered by the person applying them.

---

## Patient isolation

Patients reach their own data through dedicated `/patients/me/*` routes.
Anything addressed by id goes through one guard:

```python
def authorize_patient(self, patient_id) -> Patient:
    if self.has(Permission.PATIENT_VIEW):                 # clinical staff
        return patient
    if self.has(Permission.PATIENT_VIEW_SELF) and patient.portal_user_id == self.user.id:
        return patient                                     # their own record
    self.deny(resource_type="patient", resource_id=patient_id)   # audited, then 403
```

A cross-patient attempt is **denied and written to the audit log** with the
target's id — covered by `test_cross_patient_attempt_is_audited`.

---

## Policy storage

The default matrix lives in `app/domain/rbac_matrix.py`, version-controlled so
security policy is reviewable and diffable rather than invisible. It is seeded
into `permissions`, `roles` and `role_permissions`.

**At runtime the database is the source of truth.** Seeding is idempotent and
*additive*: it creates what is missing and never revokes a grant an
administrator made deliberately, so customisations survive a redeploy.

---

## Adding a permission

1. Add it to `Permission` in `app/domain/enums.py`
2. Describe it in `PERMISSION_DESCRIPTIONS`
3. Grant it to roles in `DEFAULT_ROLE_PERMISSIONS`
4. Guard the endpoint with `require_permission(...)`
5. Add a test asserting the roles that must **not** have it

Step 5 is not optional. The security matrix tests exist to catch a permission
quietly widening over time.

---

## Tested security matrix

From `tests/test_rbac.py`:

```
ADMIN         → admin endpoints        ALLOWED
HEALTH_WORKER → screening              ALLOWED
HEALTH_WORKER → user administration    DENIED
DOCTOR        → clinical review        ALLOWED
DOCTOR        → configuration          DENIED
PATIENT       → own record             ALLOWED
PATIENT       → another patient        DENIED  (and audited)
PATIENT       → user administration    DENIED
anonymous     → any protected route    401
demoted user  → previously allowed route  403 on the next request
```
