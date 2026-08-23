"""Administration: clinics, model registry, configuration, audit, system health.

Every figure returned here is queried from the database. Nothing is estimated,
padded or invented — an empty system reports zeros.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Access, DbSession, require_permission
from app.core.errors import NotFoundError, ValidationError
from app.domain.enums import (
    AuditAction,
    ModelStatus,
    Permission,
    ReferralStatus,
    ReviewStatus,
    RoleName,
    ScreeningState,
    SyncStatus,
    UserStatus,
    ValidationStatus,
)
from app.ml.registry import ModelRegistry
from app.models.identity import Role, User, UserRole
from app.models.organization import Clinic, Doctor, HealthWorker
from app.models.patient import Patient
from app.models.screening import (
    ClinicalReview,
    FollowUp,
    ModelMetadata,
    Referral,
    ScreeningSession,
)
from app.models.system import AuditLog, SyncQueueItem
from app.schemas.common import MessageResponse, ORMModel, Page, PaginationParams
from app.services.audit_service import AuditService
from app.services.config_service import ConfigService

router = APIRouter(tags=["administration"])

CanManageClinics = Annotated[Access, Depends(require_permission(Permission.CLINIC_MANAGE))]
CanManageModels = Annotated[Access, Depends(require_permission(Permission.MODEL_MANAGE))]
CanManageConfig = Annotated[Access, Depends(require_permission(Permission.CONFIG_MANAGE))]
CanViewAudit = Annotated[Access, Depends(require_permission(Permission.AUDIT_VIEW))]
CanViewSystem = Annotated[Access, Depends(require_permission(Permission.SYSTEM_VIEW))]


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ClinicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    location: str = Field(default="", max_length=255)
    region: str | None = Field(default=None, max_length=128)
    latitude: float | None = None
    longitude: float | None = None


class ClinicRead(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    location: str
    region: str | None
    status: str
    connectivity_status: str
    created_at: datetime


class ClinicDetail(ClinicRead):
    health_worker_count: int
    doctor_count: int
    screening_count: int
    pending_referrals: int


class ModelRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    framework: str
    deployment_target: str
    architecture: str | None = None
    input_width: int = Field(default=224, ge=32, le=2048)
    input_height: int = Field(default=224, ge=32, le=2048)
    classes: list[str] = Field(default_factory=list)
    model_path: str | None = None
    notes: str | None = None


class ModelStatusUpdate(BaseModel):
    status: ModelStatus


class ModelValidationUpdate(BaseModel):
    validation_status: ValidationStatus
    # Only ever populated from a real validation run.
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class ModelRead(ORMModel):
    id: uuid.UUID
    name: str
    version: str
    framework: str
    deployment_target: str
    architecture: str | None
    input_width: int
    input_height: int
    classes: list
    model_path: str | None
    status: str
    validation_status: str
    validation_metrics: dict
    notes: str | None
    created_at: datetime


class ConfigurationRead(ORMModel):
    id: uuid.UUID
    key: str
    value: dict
    category: str
    description: str
    is_editable: bool
    version: int
    updated_at: datetime


class ConfigurationUpdate(BaseModel):
    value: dict[str, Any]


class FeatureFlagRead(ORMModel):
    id: uuid.UUID
    key: str
    enabled: bool
    description: str


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    description: str = ""


class AuditLogRead(ORMModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    result: str
    ip_address: str | None
    context: dict
    created_at: datetime


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/admin/dashboard")
def admin_dashboard(access: CanViewSystem, db: DbSession) -> dict:
    """Counts for the admin overview — all read from the database."""

    def count(model, *conditions) -> int:
        stmt = select(func.count()).select_from(model)
        for condition in conditions:
            stmt = stmt.where(condition)
        return int(db.execute(stmt).scalar_one())

    def count_by_role(role: RoleName) -> int:
        return int(
            db.execute(
                select(func.count())
                .select_from(UserRole)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role.value)
            ).scalar_one()
        )

    today = datetime.now(tz=timezone.utc).date()

    return {
        "users": {
            "total": count(User),
            "active": count(User, User.status == UserStatus.ACTIVE.value),
            "health_workers": count_by_role(RoleName.HEALTH_WORKER),
            "doctors": count_by_role(RoleName.DOCTOR),
            "patients": count_by_role(RoleName.PATIENT),
        },
        "patients": {"total": count(Patient)},
        "clinics": {
            "total": count(Clinic),
            "active": count(Clinic, Clinic.status == "active"),
        },
        "screenings": {
            "total": count(ScreeningSession),
            "completed": count(
                ScreeningSession, ScreeningSession.state == ScreeningState.COMPLETED.value
            ),
            "in_progress": count(
                ScreeningSession,
                ScreeningSession.state.notin_(
                    [ScreeningState.COMPLETED.value, ScreeningState.CANCELLED.value]
                ),
            ),
            "captured_offline": count(
                ScreeningSession, ScreeningSession.captured_offline.is_(True)
            ),
        },
        "reviews": {
            "pending": count(
                ClinicalReview, ClinicalReview.status == ReviewStatus.PENDING.value
            ),
            "in_review": count(
                ClinicalReview, ClinicalReview.status == ReviewStatus.IN_REVIEW.value
            ),
            "completed": count(
                ClinicalReview, ClinicalReview.status == ReviewStatus.COMPLETED.value
            ),
        },
        "referrals": {
            "total": count(Referral),
            "pending": count(Referral, Referral.status == ReferralStatus.CREATED.value),
        },
        "follow_ups": {
            "total": count(FollowUp),
            "due": count(FollowUp, FollowUp.due_date <= today),
        },
        "sync": {
            "pending": count(SyncQueueItem, SyncQueueItem.status == SyncStatus.PENDING.value),
            "failed": count(SyncQueueItem, SyncQueueItem.status == SyncStatus.FAILED.value),
        },
        "model": ModelRegistry(db).status(),
    }


@router.get("/admin/system-health")
def system_health(access: CanViewSystem, db: DbSession) -> dict:
    """Live dependency checks — database, object storage, model provider."""
    from sqlalchemy import text

    from app.core.config import settings
    from app.storage import get_storage_provider

    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        database_ok = False

    storage_ok = True
    storage_detail = settings.storage_provider.value
    try:
        get_storage_provider()
    except Exception as exc:  # noqa: BLE001
        storage_ok = False
        storage_detail = f"unavailable: {type(exc).__name__}"

    model_status = ModelRegistry(db).status()

    return {
        "database": {"ok": database_ok, "engine": "sqlite" if settings.is_sqlite else "postgresql"},
        "storage": {"ok": storage_ok, "provider": storage_detail},
        "model": {
            "ok": bool(model_status.get("available")),
            "version": model_status.get("model_version"),
            "development": model_status.get("is_development_model"),
            "validation_status": model_status.get("validation_status"),
        },
        "environment": settings.env.value,
    }


# --------------------------------------------------------------------------- #
# Clinics
# --------------------------------------------------------------------------- #
@router.get("/clinics", response_model=Page[ClinicDetail])
def list_clinics(
    access: Access,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[ClinicDetail]:
    params = PaginationParams(page=page, page_size=page_size)
    total = int(db.execute(select(func.count()).select_from(Clinic)).scalar_one())
    rows = (
        db.execute(
            select(Clinic)
            .order_by(Clinic.name)
            .limit(params.page_size)
            .offset(params.offset)
        )
        .scalars()
        .all()
    )

    def count(model, condition) -> int:
        return int(
            db.execute(select(func.count()).select_from(model).where(condition)).scalar_one()
        )

    items = [
        ClinicDetail(
            **ClinicRead.model_validate(clinic).model_dump(),
            health_worker_count=count(HealthWorker, HealthWorker.clinic_id == clinic.id),
            doctor_count=count(Doctor, Doctor.clinic_id == clinic.id),
            screening_count=count(
                ScreeningSession, ScreeningSession.clinic_id == clinic.id
            ),
            pending_referrals=count(
                Referral,
                (Referral.to_clinic_id == clinic.id)
                & (Referral.status == ReferralStatus.CREATED.value),
            ),
        )
        for clinic in rows
    ]
    return Page.build(items, total, params)


@router.post("/clinics", response_model=ClinicRead, status_code=status.HTTP_201_CREATED)
def create_clinic(
    payload: ClinicCreate, access: CanManageClinics, db: DbSession
) -> ClinicRead:
    from app.core.errors import ConflictError

    if db.execute(select(Clinic).where(Clinic.code == payload.code)).scalars().first():
        raise ConflictError(f"Clinic code '{payload.code}' is already in use.")

    clinic = Clinic(**payload.model_dump())
    db.add(clinic)
    db.flush()
    AuditService(db).record(
        action=AuditAction.CONFIG_CHANGED,
        actor=access.user,
        resource_type="clinic",
        resource_id=clinic.id,
        context={"event": "clinic_created", "code": clinic.code},
    )
    db.commit()
    return ClinicRead.model_validate(clinic)


# --------------------------------------------------------------------------- #
# Model registry
# --------------------------------------------------------------------------- #
@router.get("/models", response_model=list[ModelRead])
def list_models(access: CanManageModels, db: DbSession) -> list[ModelRead]:
    rows = (
        db.execute(select(ModelMetadata).order_by(ModelMetadata.created_at.desc()))
        .scalars()
        .all()
    )
    return [ModelRead.model_validate(r) for r in rows]


@router.get("/models/status")
def model_status(access: Access, db: DbSession) -> dict:
    """Honest model status. Never asserts validation that has not happened."""
    return ModelRegistry(db).status()


@router.post("/models", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def register_model(
    payload: ModelRegisterRequest, access: CanManageModels, db: DbSession
) -> ModelRead:
    """Register a model. It starts REGISTERED and NOT clinically validated."""
    from app.core.errors import ConflictError

    duplicate = (
        db.execute(
            select(ModelMetadata).where(
                ModelMetadata.name == payload.name, ModelMetadata.version == payload.version
            )
        )
        .scalars()
        .first()
    )
    if duplicate is not None:
        raise ConflictError(f"Model '{payload.name}:{payload.version}' already exists.")

    model = ModelMetadata(
        **payload.model_dump(),
        status=ModelStatus.REGISTERED.value,
        validation_status=ValidationStatus.NOT_VALIDATED.value,
        validation_metrics={},
        registered_by_user_id=access.user.id,
    )
    db.add(model)
    db.flush()
    AuditService(db).record(
        action=AuditAction.MODEL_REGISTERED,
        actor=access.user,
        resource_type="model_metadata",
        resource_id=model.id,
        context={"name": model.name, "version": model.version},
    )
    db.commit()
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/status", response_model=ModelRead)
def set_model_status(
    model_id: uuid.UUID,
    payload: ModelStatusUpdate,
    access: CanManageModels,
    db: DbSession,
) -> ModelRead:
    """Advance the model lifecycle. Only one model may be ACTIVE at a time."""
    model = db.get(ModelMetadata, model_id)
    if model is None:
        raise NotFoundError("Model not found.")

    if payload.status == ModelStatus.ACTIVE:
        if model.validation_status == ValidationStatus.FAILED.value:
            raise ValidationError("A model that failed validation cannot be activated.")
        for other in (
            db.execute(
                select(ModelMetadata).where(
                    ModelMetadata.status == ModelStatus.ACTIVE.value,
                    ModelMetadata.id != model.id,
                )
            )
            .scalars()
            .all()
        ):
            other.status = ModelStatus.DEPRECATED.value

    previous = model.status
    model.status = payload.status.value
    db.flush()
    AuditService(db).record(
        action=AuditAction.MODEL_STATUS_CHANGED,
        actor=access.user,
        resource_type="model_metadata",
        resource_id=model.id,
        context={"from": previous, "to": model.status},
    )
    db.commit()
    return ModelRead.model_validate(model)


@router.post("/models/{model_id}/validation", response_model=ModelRead)
def set_model_validation(
    model_id: uuid.UUID,
    payload: ModelValidationUpdate,
    access: CanManageModels,
    db: DbSession,
) -> ModelRead:
    """Record the outcome of a real validation run.

    Marking a model VALIDATED requires accompanying metrics — a validation
    claim with no evidence is rejected.
    """
    model = db.get(ModelMetadata, model_id)
    if model is None:
        raise NotFoundError("Model not found.")

    if payload.validation_status == ValidationStatus.VALIDATED and not payload.validation_metrics:
        raise ValidationError(
            "Validation metrics are required to mark a model as clinically validated."
        )

    model.validation_status = payload.validation_status.value
    model.validation_metrics = payload.validation_metrics
    if payload.notes:
        model.notes = payload.notes
    db.flush()
    AuditService(db).record(
        action=AuditAction.MODEL_STATUS_CHANGED,
        actor=access.user,
        resource_type="model_metadata",
        resource_id=model.id,
        context={"validation_status": model.validation_status},
    )
    db.commit()
    return ModelRead.model_validate(model)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@router.get("/config", response_model=list[ConfigurationRead])
def list_configuration(
    access: CanManageConfig, db: DbSession, category: str | None = Query(default=None)
) -> list[ConfigurationRead]:
    service = ConfigService(db)
    service.seed_defaults()
    db.commit()
    return [ConfigurationRead.model_validate(r) for r in service.list_all(category=category)]


@router.get("/config/{key}")
def get_configuration(key: str, access: CanManageConfig, db: DbSession) -> dict:
    return {"key": key, "value": ConfigService(db).get(key)}


@router.put("/config/{key}", response_model=ConfigurationRead)
def update_configuration(
    key: str, payload: ConfigurationUpdate, access: CanManageConfig, db: DbSession
) -> ConfigurationRead:
    row = ConfigService(db).set(key, payload.value, actor=access.user)
    return ConfigurationRead.model_validate(row)


@router.post("/config/{key}/reset", response_model=ConfigurationRead)
def reset_configuration(
    key: str, access: CanManageConfig, db: DbSession
) -> ConfigurationRead:
    row = ConfigService(db).reset_to_default(key, actor=access.user)
    return ConfigurationRead.model_validate(row)


@router.get("/config-flags", response_model=list[FeatureFlagRead])
def list_flags(access: CanManageConfig, db: DbSession) -> list[FeatureFlagRead]:
    return [FeatureFlagRead.model_validate(f) for f in ConfigService(db).list_flags()]


@router.put("/config-flags/{key}", response_model=FeatureFlagRead)
def set_flag(
    key: str, payload: FeatureFlagUpdate, access: CanManageConfig, db: DbSession
) -> FeatureFlagRead:
    flag = ConfigService(db).set_flag(
        key, payload.enabled, actor=access.user, description=payload.description
    )
    return FeatureFlagRead.model_validate(flag)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
@router.get("/audit", response_model=Page[AuditLogRead])
def list_audit_logs(
    access: CanViewAudit,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    result: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> Page[AuditLogRead]:
    from app.repositories.audit_repository import AuditRepository

    repo = AuditRepository(db)
    params = PaginationParams(page=page, page_size=page_size)
    stmt = repo.search_statement(
        action=action,
        resource_type=resource_type,
        result=result,
        date_from=date_from,
        date_to=date_to,
    )
    rows, total = repo.paginate(stmt, limit=params.page_size, offset=params.offset)
    return Page.build([AuditLogRead.model_validate(r) for r in rows], total, params)


@router.get("/audit/me", response_model=Page[AuditLogRead])
def list_own_audit_logs(
    access: Access,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AuditLogRead]:
    """A clinician's own activity trail — no elevated permission needed."""
    from app.repositories.audit_repository import AuditRepository

    repo = AuditRepository(db)
    params = PaginationParams(page=page, page_size=page_size)
    stmt = repo.search_statement(actor_user_id=access.user.id)
    rows, total = repo.paginate(stmt, limit=params.page_size, offset=params.offset)
    return Page.build([AuditLogRead.model_validate(r) for r in rows], total, params)
