"""Default role → permission security policy.

This is the *initial* policy, deliberately version-controlled so it is
reviewable in code review and diffable over time (security policy should never
be invisible). At runtime the **database is the source of truth**: an admin can
change role assignments through ``/api/v1/config`` and every change is audited.

The seeder applies this matrix idempotently; it never revokes permissions an
administrator has deliberately granted through the API.
"""

from __future__ import annotations

from app.domain.enums import Permission as P
from app.domain.enums import RoleName

ROLE_DEFINITIONS: dict[RoleName, dict[str, str]] = {
    RoleName.ADMIN: {
        "display_name": "Administrator",
        "description": "Platform administration, configuration and oversight.",
    },
    RoleName.HEALTH_WORKER: {
        "display_name": "Health Worker",
        "description": "Field screening: patient registration, capture and referral.",
    },
    RoleName.DOCTOR: {
        "display_name": "Doctor",
        "description": "Clinical review of screenings, referrals and follow-ups.",
    },
    RoleName.PATIENT: {
        "display_name": "Patient",
        "description": "Access to one's own screening results and follow-ups.",
    },
}

PERMISSION_DESCRIPTIONS: dict[P, tuple[str, str]] = {
    P.PATIENT_VIEW_SELF: ("View one's own patient record", "patient"),
    P.PATIENT_VIEW: ("View patient records", "patient"),
    P.PATIENT_CREATE: ("Register new patients", "patient"),
    P.PATIENT_UPDATE: ("Update patient records", "patient"),
    P.SCREENING_CREATE: ("Start and conduct screenings", "screening"),
    P.SCREENING_VIEW: ("View screening sessions", "screening"),
    P.IMAGE_VIEW: ("View retinal images", "imaging"),
    P.IMAGE_UPLOAD: ("Upload retinal images", "imaging"),
    P.INFERENCE_RUN: ("Run AI screening inference", "ai"),
    P.EXPLANATION_VIEW: ("View AI explanations (Grad-CAM)", "ai"),
    P.RISK_VIEW: ("View risk assessments", "clinical"),
    P.REFERRAL_CREATE: ("Create referrals", "clinical"),
    P.REFERRAL_VIEW: ("View referrals", "clinical"),
    P.CLINICAL_REVIEW: ("Perform clinical review of screenings", "clinical"),
    P.FOLLOWUP_MANAGE: ("Create and manage follow-ups", "clinical"),
    P.SYNC_WRITE: ("Submit offline sync batches", "sync"),
    P.USER_MANAGE: ("Create and manage user accounts", "administration"),
    P.CLINIC_MANAGE: ("Manage clinics", "administration"),
    P.MODEL_MANAGE: ("Manage the model registry and lifecycle", "administration"),
    P.CONFIG_MANAGE: ("Manage system configuration and feature flags", "administration"),
    P.AUDIT_VIEW: ("View the full audit log", "administration"),
    P.SYSTEM_VIEW: ("View system health and metrics", "administration"),
}

# NOTE: ADMIN intentionally does NOT hold CLINICAL_REVIEW — administration and
# clinical decision-making are separated. Only a doctor signs off on a case.
DEFAULT_ROLE_PERMISSIONS: dict[RoleName, list[P]] = {
    RoleName.ADMIN: [
        P.USER_MANAGE,
        P.CLINIC_MANAGE,
        P.MODEL_MANAGE,
        P.CONFIG_MANAGE,
        P.AUDIT_VIEW,
        P.SYSTEM_VIEW,
        P.PATIENT_VIEW,
        P.SCREENING_VIEW,
        P.REFERRAL_VIEW,
        P.RISK_VIEW,
    ],
    RoleName.HEALTH_WORKER: [
        P.PATIENT_CREATE,
        P.PATIENT_VIEW,
        P.PATIENT_UPDATE,
        P.SCREENING_CREATE,
        P.SCREENING_VIEW,
        P.IMAGE_UPLOAD,
        P.IMAGE_VIEW,
        P.INFERENCE_RUN,
        P.EXPLANATION_VIEW,
        P.RISK_VIEW,
        P.REFERRAL_CREATE,
        P.REFERRAL_VIEW,
        P.FOLLOWUP_MANAGE,
        P.SYNC_WRITE,
    ],
    RoleName.DOCTOR: [
        P.PATIENT_VIEW,
        P.SCREENING_VIEW,
        P.IMAGE_VIEW,
        P.EXPLANATION_VIEW,
        P.RISK_VIEW,
        P.REFERRAL_VIEW,
        P.REFERRAL_CREATE,
        P.CLINICAL_REVIEW,
        P.FOLLOWUP_MANAGE,
    ],
    RoleName.PATIENT: [
        # Patients reach their own data through /patients/me/* endpoints, which
        # additionally enforce record ownership.
        P.PATIENT_VIEW_SELF,
    ],
}
