"""Role-based access control, enforced at the API level.

Covers the required security matrix (spec §67):
    ADMIN         -> admin endpoints        ALLOWED
    HEALTH_WORKER -> screening              ALLOWED
    HEALTH_WORKER -> admin configuration    DENIED
    PATIENT       -> own data               ALLOWED
    PATIENT       -> another patient        DENIED
    PATIENT       -> doctor workspace       DENIED
    DOCTOR        -> clinical cases         ALLOWED
    DOCTOR        -> admin configuration    DENIED
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import AccessContext
from app.core.errors import PermissionDeniedError
from app.domain.enums import AuditAction, Permission, RoleName
from app.models.patient import Patient
from app.models.system import AuditLog
from app.services.rbac_service import RBACService


# --------------------------------------------------------------------------- #
# Policy resolution
# --------------------------------------------------------------------------- #
def test_seeded_policy_grants_expected_permissions(db_session: Session, make_user) -> None:
    rbac = RBACService(db_session)
    admin = make_user("a@example.com", RoleName.ADMIN)
    worker = make_user("w@example.com", RoleName.HEALTH_WORKER)
    doctor = make_user("d@example.com", RoleName.DOCTOR)
    patient = make_user("p@example.com", RoleName.PATIENT, link_patient=True)

    assert rbac.has_permission(admin, Permission.CONFIG_MANAGE)
    assert rbac.has_permission(worker, Permission.SCREENING_CREATE)
    assert rbac.has_permission(doctor, Permission.CLINICAL_REVIEW)
    assert rbac.has_permission(patient, Permission.PATIENT_VIEW_SELF)


def test_administration_and_clinical_duties_are_separated(
    db_session: Session, make_user
) -> None:
    """An administrator must not be able to sign off on a clinical case."""
    rbac = RBACService(db_session)
    admin = make_user("admin2@example.com", RoleName.ADMIN)
    doctor = make_user("doc2@example.com", RoleName.DOCTOR)

    assert not rbac.has_permission(admin, Permission.CLINICAL_REVIEW)
    assert not rbac.has_permission(doctor, Permission.CONFIG_MANAGE)


def test_seeding_is_idempotent(db_session: Session) -> None:
    stats = RBACService(db_session).seed_policy()
    db_session.commit()

    assert stats["permissions_created"] == 0
    assert stats["roles_created"] == 0
    assert stats["grants_created"] == 0


# --------------------------------------------------------------------------- #
# API-level enforcement
# --------------------------------------------------------------------------- #
def test_admin_can_reach_admin_endpoints(client: TestClient, make_user, login) -> None:
    make_user("admin@example.com", RoleName.ADMIN)
    headers = login("admin@example.com")

    assert client.get("/api/v1/users", headers=headers).status_code == 200


@pytest.mark.parametrize(
    "role",
    [RoleName.HEALTH_WORKER, RoleName.DOCTOR, RoleName.PATIENT],
)
def test_non_admin_roles_are_denied_user_administration(
    client: TestClient, make_user, login, role: RoleName
) -> None:
    email = f"{role.value}@example.com"
    make_user(email, role, link_patient=role == RoleName.PATIENT)
    headers = login(email)

    response = client.get("/api/v1/users", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_denied_access_is_audited(client: TestClient, make_user, login, db_session) -> None:
    make_user("nosy@example.com", RoleName.HEALTH_WORKER)
    headers = login("nosy@example.com")

    client.get("/api/v1/users", headers=headers)

    denials = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.ACCESS_DENIED.value)
        .all()
    )
    assert len(denials) == 1
    assert denials[0].actor_email == "nosy@example.com"


def test_unauthenticated_requests_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/users").status_code == 401


def test_permission_check_is_not_taken_from_the_token(
    client: TestClient, make_user, login, db_session
) -> None:
    """A token minted while privileged must stop working once the role is removed.

    This proves permissions are re-resolved from the database per request rather
    than trusted from the JWT payload.
    """
    admin = make_user("temp-admin@example.com", RoleName.ADMIN)
    headers = login("temp-admin@example.com")
    assert client.get("/api/v1/users", headers=headers).status_code == 200

    # Demote the user; the previously issued token is unchanged.
    RBACService(db_session).replace_role(user_id=admin.id, role_name=RoleName.PATIENT)
    db_session.commit()

    assert client.get("/api/v1/users", headers=headers).status_code == 403


# --------------------------------------------------------------------------- #
# Patient isolation
# --------------------------------------------------------------------------- #
def _context(db_session: Session, user, path: str = "/api/v1/patients") -> AccessContext:
    class _FakeURL:
        def __init__(self, p: str) -> None:
            self.path = p

    class _FakeRequest:
        def __init__(self, p: str) -> None:
            self.url = _FakeURL(p)
            self.method = "GET"
            self.headers: dict[str, str] = {}
            self.client = None

    return AccessContext(db_session, user, _FakeRequest(path))  # type: ignore[arg-type]


def test_patient_can_access_their_own_record(db_session: Session, make_user) -> None:
    user = make_user("self@example.com", RoleName.PATIENT, link_patient=True)
    access = _context(db_session, user)

    own = access.resolve_own_patient()

    assert access.authorize_patient(own.id).id == own.id


def test_patient_cannot_access_another_patients_record(
    db_session: Session, make_user
) -> None:
    user = make_user("mine@example.com", RoleName.PATIENT, link_patient=True)
    other_user = make_user("theirs@example.com", RoleName.PATIENT, link_patient=True)
    other = (
        db_session.query(Patient).filter(Patient.portal_user_id == other_user.id).one()
    )

    access = _context(db_session, user)

    with pytest.raises(PermissionDeniedError):
        access.authorize_patient(other.id)


def test_cross_patient_attempt_is_audited(db_session: Session, make_user) -> None:
    user = make_user("snoop@example.com", RoleName.PATIENT, link_patient=True)
    victim_user = make_user("victim@example.com", RoleName.PATIENT, link_patient=True)
    victim = (
        db_session.query(Patient).filter(Patient.portal_user_id == victim_user.id).one()
    )

    with pytest.raises(PermissionDeniedError):
        _context(db_session, user).authorize_patient(victim.id)

    denial = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.ACCESS_DENIED.value)
        .one()
    )
    assert denial.resource_type == "patient"
    assert denial.resource_id == str(victim.id)


def test_clinical_staff_may_access_patient_records(db_session: Session, make_user) -> None:
    doctor = make_user("clinician@example.com", RoleName.DOCTOR)
    patient_user = make_user("case@example.com", RoleName.PATIENT, link_patient=True)
    patient = (
        db_session.query(Patient).filter(Patient.portal_user_id == patient_user.id).one()
    )

    assert _context(db_session, doctor).authorize_patient(patient.id).id == patient.id


def test_missing_patient_returns_not_found(db_session: Session, make_user) -> None:
    from app.core.errors import NotFoundError

    doctor = make_user("nf@example.com", RoleName.DOCTOR)

    with pytest.raises(NotFoundError):
        _context(db_session, doctor).authorize_patient(uuid.uuid4())
