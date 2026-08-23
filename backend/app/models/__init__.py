"""SQLAlchemy models.

Importing this package registers every mapper on ``Base.metadata`` — required
for Alembic autogenerate and for ``create_all`` in tests.
"""

from app.models.identity import (
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.models.organization import Clinic, Doctor, HealthWorker
from app.models.patient import Patient, PatientConsent
from app.models.screening import (
    ClinicalReview,
    Explanation,
    FollowUp,
    InferenceResult,
    ModelMetadata,
    QualityAssessment,
    Referral,
    RetinalImage,
    RiskAssessment,
    ScreeningSession,
)
from app.models.system import AuditLog, FeatureFlag, SyncQueueItem, SystemConfiguration

__all__ = [
    "AuditLog",
    "Clinic",
    "ClinicalReview",
    "Doctor",
    "Explanation",
    "FeatureFlag",
    "FollowUp",
    "HealthWorker",
    "InferenceResult",
    "ModelMetadata",
    "Patient",
    "PatientConsent",
    "Permission",
    "QualityAssessment",
    "Referral",
    "RefreshToken",
    "RetinalImage",
    "RiskAssessment",
    "Role",
    "RolePermission",
    "ScreeningSession",
    "SyncQueueItem",
    "SystemConfiguration",
    "User",
    "UserRole",
]
