"""Seed a runnable demo scenario.

Creates a clinic, staff accounts, patients, and completed screenings driven
through the *real* workflow — the same services the API uses, so consent, the
quality gate, inference, Grad-CAM, risk and referral all actually run.

The retinal images are real APTOS scans already on this machine. The people are
invented.

    SYNTHETIC DEVELOPMENT DATA — NOT REAL PATIENT DATA

Every patient created here is prefixed DEMO- so it is obvious in any UI, and the
script refuses to run against a production environment.

Usage:
    python -m scripts.seed_demo
"""

from __future__ import annotations

import os
import random
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.domain.enums import (
    ConsentType,
    EyeSide,
    ReviewDecision,
    RoleName,
    UserStatus,
)
from app.models.identity import User
from app.models.organization import Clinic, Doctor, HealthWorker
from app.services.config_service import ConfigService
from app.services.patient_service import PatientService
from app.services.rbac_service import RBACService
from app.services.review_service import ReviewService
from app.services.screening_service import ScreeningService

logger = get_logger(__name__)

def _demo_password() -> str:
    """Password for the seeded demo accounts.

    Taken from RS_DEMO_PASSWORD when set, otherwise generated fresh for this
    run and printed at the end.

    It used to be a literal in this file. A working credential committed to a
    public repository is a working credential no matter how clearly it is
    labelled "demo" — and this script seeds accounts with real clinical
    permissions, so anyone who ran it against a reachable database inherited a
    known password for a doctor account. Generating it means the repository
    never contains one.
    """
    configured = os.environ.get("RS_DEMO_PASSWORD", "").strip()
    if configured:
        return configured
    # token_urlsafe(18) is 24 characters, comfortably over the configured
    # minimum length; the affixes guarantee mixed classes whatever it yields.
    return f"Demo-{secrets.token_urlsafe(18)}-7"


DEMO_PASSWORD = _demo_password()
APTOS_CACHE = REPO_ROOT / "ml" / "data" / "aptos_224"  # cropped 224px cache

# (name, age-ish context, diabetes years, which APTOS grade folder to draw from)
DEMO_PATIENTS = [
    ("Aarti Deshmukh", True, 12, "proliferative"),
    ("Ramesh Patil", True, 9, "severe"),
    ("Sunita Kale", True, 6, "moderate"),
    ("Vikram Jadhav", True, 3, "mild"),
    ("Meena Shinde", True, 2, "no_dr"),
    ("Prakash Gaikwad", True, 15, "severe"),
    ("Lata Bhosale", True, 4, "moderate"),
    ("Sanjay More", False, None, "no_dr"),
]


def create_user(db, *, email: str, name: str, role: RoleName) -> User:
    from app.repositories.user_repository import UserRepository

    existing = UserRepository(db).get_by_email(email)
    if existing:
        return existing

    user = User(
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=name,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    db.flush()
    RBACService(db).assign_role(user_id=user.id, role_name=role)
    return user


def pick_images(grade: str, count: int = 2) -> list[bytes]:
    folder = APTOS_CACHE / grade
    files = sorted(folder.glob("*.png"))
    if not files:
        raise SystemExit(
            f"No cached APTOS images at {folder}.\n"
            "Run: cd ml && python -m datasets.cache_preprocessed "
            "--data-dir data/aptos --output data/aptos_224"
        )
    chosen = random.Random(hash(grade) & 0xFFFF).sample(files, min(count, len(files)))
    return [p.read_bytes() for p in chosen]


def main() -> None:
    if settings.is_production:
        raise SystemExit("Refusing to seed demo data into a production environment.")

    random.seed(7)
    print("SYNTHETIC DEVELOPMENT DATA — NOT REAL PATIENT DATA\n")

    with SessionLocal() as db:
        ConfigService(db).seed_defaults()
        db.commit()

        clinic = db.query(Clinic).filter(Clinic.code == "DEMO-PHC-01").one_or_none()
        if clinic is None:
            clinic = Clinic(
                name="Shirur Primary Health Centre",
                code="DEMO-PHC-01",
                location="Shirur, Pune District",
                region="Maharashtra",
                status="active",
                connectivity_status="intermittent",
            )
            db.add(clinic)
            db.flush()

        worker_user = create_user(
            db, email="worker@retinasight.ai", name="Nurse Kavita Rane",
            role=RoleName.HEALTH_WORKER,
        )
        if not db.query(HealthWorker).filter(HealthWorker.user_id == worker_user.id).count():
            db.add(HealthWorker(user_id=worker_user.id, clinic_id=clinic.id, staff_code="HW-014"))

        doctor_user = create_user(
            db, email="doctor@retinasight.ai", name="Dr Anil Kulkarni",
            role=RoleName.DOCTOR,
        )
        if not db.query(Doctor).filter(Doctor.user_id == doctor_user.id).count():
            db.add(
                Doctor(
                    user_id=doctor_user.id, clinic_id=clinic.id,
                    specialty="ophthalmology", license_number="DEMO-MH-4471",
                )
            )
        db.commit()
        print(f"clinic  : {clinic.name}")
        print(f"worker  : {worker_user.email}")
        print(f"doctor  : {doctor_user.email}\n")

        patients = PatientService(db)
        screenings = ScreeningService(db)
        reviews = ReviewService(db)

        created = 0
        for name, diabetic, years, grade in DEMO_PATIENTS:
            patient = patients.register(
                full_name=name,
                patient_code=f"DEMO-{created + 1:04d}",
                has_diabetes=diabetic,
                diabetes_duration_years=years,
                clinic_id=clinic.id,
                actor=worker_user,
                consents={
                    ConsentType.SCREENING.value: True,
                    ConsentType.DATA_STORAGE.value: True,
                },
            )

            session = screenings.start_screening(
                patient_id=patient.id, actor=worker_user, clinic_id=clinic.id
            )

            images = pick_images(grade, 2)
            for eye, data in zip((EyeSide.LEFT, EyeSide.RIGHT), images):
                outcome = screenings.capture_eye(
                    session_id=session.id, eye_side=eye, data=data, actor=worker_user
                )
                status = "accepted" if not outcome.retake_required else "retake"
                print(f"  {name:<20} {eye.value:<6} quality {status}")

            try:
                screenings.mark_ready_for_inference(session.id)
                result = screenings.run_inference(session.id, actor=worker_user)
                risk = result["risk"]
                worst = result["worst"]
                print(
                    f"  {name:<20} -> {worst.category:<14} "
                    f"conf {worst.confidence:.2f}  risk {risk.risk_level}"
                )

                referral = screenings.create_referral(session.id, actor=worker_user)
                review = screenings.submit_for_review(session.id, actor=worker_user)

                # Leave the two most severe cases pending so the doctor's queue
                # has something waiting.
                if grade not in {"proliferative", "severe"}:
                    reviews.claim(review.id, reviewer=doctor_user)
                    reviews.complete(
                        review.id,
                        reviewer=doctor_user,
                        decision=ReviewDecision.CONFIRM_AI,
                        clinician_category=worst.category,
                        notes="Reviewed images and heat map. Consistent with the AI result.",
                    )
                if referral:
                    print(f"  {name:<20} referral {referral.priority}")
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:<20} screening incomplete: {exc}")

            created += 1
            print()

        print(f"\n{created} demo patients screened.")
        source = (
            "from RS_DEMO_PASSWORD"
            if os.environ.get("RS_DEMO_PASSWORD", "").strip()
            else "generated for this run — set RS_DEMO_PASSWORD to keep it stable"
        )
        print("\nSign in with:")
        print(f"  admin   {settings.seed_admin_email} / {settings.seed_admin_password}")
        print(f"  worker  worker@retinasight.ai / {DEMO_PASSWORD}")
        print(f"  doctor  doctor@retinasight.ai / {DEMO_PASSWORD}")
        print(f"\n  (demo password {source})")


if __name__ == "__main__":
    main()
