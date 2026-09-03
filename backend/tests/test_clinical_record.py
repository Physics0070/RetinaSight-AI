"""Medical history and prescribing.

Two things are being protected here. First, that the record behaves like a
medical record: entries are editable, corrections are soft-deleted rather than
destroyed, and every mutation is audited. Second, that authority is separated —
a field worker may read history but never write it, and only a clinician may
prescribe. An administrator has oversight and no prescribing power at all.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import AuditAction, RoleName
from app.models.clinical_record import PatientHistoryEntry
from app.models.patient import Patient
from app.models.system import AuditLog


def _patient(db: Session, code: str = "PT-REC-1") -> Patient:
    patient = Patient(patient_code=code, full_name="History Subject")
    db.add(patient)
    db.commit()
    return patient


def _entry(client: TestClient, headers: dict, patient_id, **overrides) -> dict:
    payload = {
        "entry_type": "condition",
        "title": "Type 2 diabetes mellitus",
        "detail": "Diagnosed at the district hospital.",
        "occurred_on": "2019-04-02",
        "status": "ongoing",
        **overrides,
    }
    response = client.post(
        f"/api/v1/patients/{patient_id}/history", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# History: the doctor's record
# --------------------------------------------------------------------------- #
def test_doctor_can_add_view_and_edit_history(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("doc-hist@example.com", RoleName.DOCTOR)
    headers = login("doc-hist@example.com")
    patient = _patient(db_session)

    created = _entry(client, headers, patient.id)
    assert created["title"] == "Type 2 diabetes mellitus"
    assert created["entry_type"] == "condition"

    listed = client.get(f"/api/v1/patients/{patient.id}/history", headers=headers)
    assert listed.status_code == 200
    assert [e["id"] for e in listed.json()] == [created["id"]]

    edited = client.patch(
        f"/api/v1/history/{created['id']}",
        json={"status": "resolved", "detail": "Controlled on metformin."},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "resolved"
    # A partial edit must not blank the fields it did not mention.
    assert edited.json()["title"] == "Type 2 diabetes mellitus"


def test_history_is_ordered_newest_clinical_event_first(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("doc-order@example.com", RoleName.DOCTOR)
    headers = login("doc-order@example.com")
    patient = _patient(db_session, "PT-REC-ORDER")

    _entry(client, headers, patient.id, title="Older", occurred_on="2015-01-01")
    _entry(client, headers, patient.id, title="Newer", occurred_on="2023-06-01")

    titles = [e["title"] for e in client.get(
        f"/api/v1/patients/{patient.id}/history", headers=headers
    ).json()]
    assert titles == ["Newer", "Older"]


def test_removing_an_entry_hides_it_but_keeps_the_row(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    """A medical record that can be silently erased is not a medical record."""
    make_user("doc-del@example.com", RoleName.DOCTOR)
    headers = login("doc-del@example.com")
    patient = _patient(db_session, "PT-REC-DEL")
    created = _entry(client, headers, patient.id)

    assert client.delete(f"/api/v1/history/{created['id']}", headers=headers).status_code == 204

    visible = client.get(f"/api/v1/patients/{patient.id}/history", headers=headers).json()
    assert visible == []

    # The row survives, and an audit view can still retrieve it.
    audit_view = client.get(
        f"/api/v1/patients/{patient.id}/history",
        params={"include_removed": True},
        headers=headers,
    ).json()
    assert [e["id"] for e in audit_view] == [created["id"]]
    assert db_session.get(PatientHistoryEntry, uuid.UUID(created["id"])) is not None


def test_history_mutations_are_audited(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("doc-audit@example.com", RoleName.DOCTOR)
    headers = login("doc-audit@example.com")
    patient = _patient(db_session, "PT-REC-AUDIT")

    created = _entry(client, headers, patient.id)
    client.patch(
        f"/api/v1/history/{created['id']}", json={"status": "resolved"}, headers=headers
    )
    client.delete(f"/api/v1/history/{created['id']}", headers=headers)

    actions = {row.action for row in db_session.query(AuditLog).all()}
    assert AuditAction.HISTORY_ENTRY_ADDED.value in actions
    assert AuditAction.HISTORY_ENTRY_UPDATED.value in actions
    assert AuditAction.HISTORY_ENTRY_REMOVED.value in actions


# --------------------------------------------------------------------------- #
# Prescribing
# --------------------------------------------------------------------------- #
def test_doctor_can_prescribe_and_the_prescriber_is_recorded(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    doctor = make_user("doc-rx@example.com", RoleName.DOCTOR)
    headers = login("doc-rx@example.com")
    patient = _patient(db_session, "PT-RX-1")

    response = client.post(
        f"/api/v1/patients/{patient.id}/prescriptions",
        json={
            "diagnosis": "Moderate non-proliferative diabetic retinopathy",
            "items": [
                {
                    "name": "Metformin",
                    "dose": "500 mg",
                    "frequency": "twice daily",
                    "duration": "3 months",
                    "instructions": "With food.",
                }
            ],
            "notes": "Review after retinal photography in 3 months.",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["items"][0]["name"] == "Metformin"
    # The signature on the document: who prescribed it.
    assert body["prescribed_by_user_id"] == str(doctor.id)


def test_prescription_needs_at_least_one_medicine(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("doc-empty@example.com", RoleName.DOCTOR)
    headers = login("doc-empty@example.com")
    patient = _patient(db_session, "PT-RX-EMPTY")

    response = client.post(
        f"/api/v1/patients/{patient.id}/prescriptions", json={"items": []}, headers=headers
    )
    assert response.status_code == 422


def test_duplicate_medicine_is_rejected(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    """Two lines for one drug is a dosing error waiting to happen."""
    make_user("doc-dupe@example.com", RoleName.DOCTOR)
    headers = login("doc-dupe@example.com")
    patient = _patient(db_session, "PT-RX-DUPE")

    item = {"name": "Metformin", "dose": "500 mg", "frequency": "twice daily"}
    response = client.post(
        f"/api/v1/patients/{patient.id}/prescriptions",
        json={"items": [item, {**item, "name": "metformin"}]},
        headers=headers,
    )
    assert response.status_code == 422


def test_prescription_can_be_discontinued(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("doc-stop@example.com", RoleName.DOCTOR)
    headers = login("doc-stop@example.com")
    patient = _patient(db_session, "PT-RX-STOP")

    created = client.post(
        f"/api/v1/patients/{patient.id}/prescriptions",
        json={"items": [{"name": "Metformin", "dose": "500 mg", "frequency": "daily"}]},
        headers=headers,
    ).json()

    revised = client.patch(
        f"/api/v1/prescriptions/{created['id']}",
        json={"status": "discontinued"},
        headers=headers,
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["status"] == "discontinued"


# --------------------------------------------------------------------------- #
# Authority boundaries
# --------------------------------------------------------------------------- #
def test_health_worker_may_read_history_but_not_write_it(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("doc-w@example.com", RoleName.DOCTOR)
    make_user("worker-w@example.com", RoleName.HEALTH_WORKER)
    doctor_headers = login("doc-w@example.com")
    worker_headers = login("worker-w@example.com")
    patient = _patient(db_session, "PT-REC-WORKER")
    _entry(client, doctor_headers, patient.id)

    assert client.get(
        f"/api/v1/patients/{patient.id}/history", headers=worker_headers
    ).status_code == 200

    denied = client.post(
        f"/api/v1/patients/{patient.id}/history",
        json={"entry_type": "note", "title": "Field note"},
        headers=worker_headers,
    )
    assert denied.status_code == 403


def test_health_worker_cannot_prescribe(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    make_user("worker-rx@example.com", RoleName.HEALTH_WORKER)
    headers = login("worker-rx@example.com")
    patient = _patient(db_session, "PT-RX-WORKER")

    response = client.post(
        f"/api/v1/patients/{patient.id}/prescriptions",
        json={"items": [{"name": "Metformin", "dose": "500 mg", "frequency": "daily"}]},
        headers=headers,
    )
    assert response.status_code == 403


def test_administrator_has_oversight_but_cannot_prescribe(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    """An administrator is not a clinician."""
    make_user("admin-rx@example.com", RoleName.ADMIN)
    headers = login("admin-rx@example.com")
    patient = _patient(db_session, "PT-RX-ADMIN")

    assert client.get(
        f"/api/v1/patients/{patient.id}/prescriptions", headers=headers
    ).status_code == 200

    response = client.post(
        f"/api/v1/patients/{patient.id}/prescriptions",
        json={"items": [{"name": "Metformin", "dose": "500 mg", "frequency": "daily"}]},
        headers=headers,
    )
    assert response.status_code == 403


def test_patient_reads_own_record_and_not_anothers(
    client: TestClient, db_session: Session, make_user, login
) -> None:
    doctor = make_user("doc-iso@example.com", RoleName.DOCTOR)
    patient_user = make_user("pat-iso@example.com", RoleName.PATIENT, link_patient=True)
    doctor_headers = login("doc-iso@example.com")
    patient_headers = login("pat-iso@example.com")

    own = db_session.query(Patient).filter(Patient.portal_user_id == patient_user.id).one()
    other = _patient(db_session, "PT-REC-OTHER")
    _entry(client, doctor_headers, own.id, title="Own condition")
    _entry(client, doctor_headers, other.id, title="Someone else's condition")

    mine = client.get("/api/v1/patients/me/history", headers=patient_headers)
    assert mine.status_code == 200
    assert [e["title"] for e in mine.json()] == ["Own condition"]

    # Reaching for another patient's record by id must fail.
    assert client.get(
        f"/api/v1/patients/{other.id}/history", headers=patient_headers
    ).status_code == 403
