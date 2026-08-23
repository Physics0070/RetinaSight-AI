"""Risk engine, referral engine and the configuration service they read from."""

from __future__ import annotations

import copy
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.domain.config_defaults import (
    DEFAULT_CONFIGURATION,
    KEY_INFERENCE_POLICY,
    KEY_RISK_RULES,
)
from app.domain.enums import ReferralPriority, RiskLevel, RoleName, ScreeningCategory
from app.services.config_service import ConfigService
from app.services.referral_engine import ReferralEngine
from app.services.risk_engine import RiskEngine, RiskInput


@pytest.fixture
def config(db_session: Session) -> ConfigService:
    service = ConfigService(db_session)
    service.seed_defaults()
    db_session.commit()
    return service


def _input(
    category: str,
    confidence: float = 0.9,
    *,
    quality_ok: bool = True,
    development: bool = False,
) -> RiskInput:
    return RiskInput(
        category=category,
        confidence=confidence,
        quality_acceptable=quality_ok,
        is_development_model=development,
    )


# --------------------------------------------------------------------------- #
# Configuration service
# --------------------------------------------------------------------------- #
def test_seeding_is_idempotent(db_session: Session, config: ConfigService) -> None:
    assert config.seed_defaults() == 0


def test_missing_key_falls_back_to_the_seeded_default(db_session: Session) -> None:
    """Engines must work before anyone has touched configuration."""
    service = ConfigService(db_session)  # nothing seeded

    assert service.get(KEY_RISK_RULES)["rules"]


def test_editing_configuration_bumps_version_and_audits(
    db_session: Session, config: ConfigService, make_user
) -> None:
    from app.domain.enums import AuditAction
    from app.models.system import AuditLog

    admin = make_user("cfg@example.com", RoleName.ADMIN)
    value = copy.deepcopy(config.get(KEY_INFERENCE_POLICY))
    value["low_confidence_threshold"] = 0.8

    row = config.set(KEY_INFERENCE_POLICY, value, actor=admin)

    assert row.version == 2
    assert config.get(KEY_INFERENCE_POLICY)["low_confidence_threshold"] == 0.8
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.CONFIG_CHANGED.value)
        .count()
        == 1
    )


def test_configuration_can_be_reset_to_default(
    db_session: Session, config: ConfigService, make_user
) -> None:
    admin = make_user("reset@example.com", RoleName.ADMIN)
    value = copy.deepcopy(config.get(KEY_INFERENCE_POLICY))
    value["low_confidence_threshold"] = 0.99
    config.set(KEY_INFERENCE_POLICY, value, actor=admin)

    config.reset_to_default(KEY_INFERENCE_POLICY, actor=admin)

    expected = DEFAULT_CONFIGURATION[KEY_INFERENCE_POLICY]["value"][
        "low_confidence_threshold"
    ]
    assert config.get(KEY_INFERENCE_POLICY)["low_confidence_threshold"] == expected


def test_feature_flags_default_to_off(db_session: Session, config: ConfigService) -> None:
    assert config.is_enabled("some.unset.flag") is False

    config.set_flag("some.unset.flag", True)
    assert config.is_enabled("some.unset.flag") is True


# --------------------------------------------------------------------------- #
# Risk engine
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (ScreeningCategory.NO_DR.value, RiskLevel.LOW.value),
        (ScreeningCategory.MILD.value, RiskLevel.LOW.value),
        (ScreeningCategory.MODERATE.value, RiskLevel.MODERATE.value),
        (ScreeningCategory.SEVERE.value, RiskLevel.HIGH.value),
        (ScreeningCategory.PROLIFERATIVE.value, RiskLevel.URGENT.value),
    ],
)
def test_each_category_maps_to_its_configured_risk_band(
    db_session: Session, config: ConfigService, category: str, expected: str
) -> None:
    outcome = RiskEngine(db_session).evaluate(_input(category))

    assert outcome.risk_level == expected
    assert outcome.recommended_action


def test_failed_quality_short_circuits_to_review(
    db_session: Session, config: ConfigService
) -> None:
    """An unreliable image must never yield a reassuring 'low risk'."""
    outcome = RiskEngine(db_session).evaluate(
        _input(ScreeningCategory.NO_DR.value, quality_ok=False)
    )

    assert outcome.rule_id == "quality-insufficient"
    assert outcome.risk_level == RiskLevel.MODERATE.value
    assert outcome.requires_clinician_review is True


def test_low_confidence_raises_risk_to_the_configured_floor(
    db_session: Session, config: ConfigService
) -> None:
    outcome = RiskEngine(db_session).evaluate(
        _input(ScreeningCategory.NO_DR.value, confidence=0.20)
    )

    assert outcome.risk_level == RiskLevel.MODERATE.value
    assert any("below" in note for note in outcome.notes)


def test_low_confidence_never_lowers_an_urgent_result(
    db_session: Session, config: ConfigService
) -> None:
    outcome = RiskEngine(db_session).evaluate(
        _input(ScreeningCategory.PROLIFERATIVE.value, confidence=0.15)
    )

    assert outcome.risk_level == RiskLevel.URGENT.value


def test_every_result_requires_clinician_review(
    db_session: Session, config: ConfigService
) -> None:
    """Clinician-in-the-loop is a product invariant, not a per-case decision."""
    for category in ScreeningCategory:
        outcome = RiskEngine(db_session).evaluate(_input(category.value))
        assert outcome.requires_clinician_review is True


def test_development_model_result_is_flagged_for_review(
    db_session: Session, config: ConfigService
) -> None:
    outcome = RiskEngine(db_session).evaluate(
        _input(ScreeningCategory.NO_DR.value, development=True)
    )

    assert outcome.requires_clinician_review is True
    assert any("development model" in note.lower() for note in outcome.notes)


def test_unknown_category_falls_back_to_the_default_rule(
    db_session: Session, config: ConfigService
) -> None:
    outcome = RiskEngine(db_session).evaluate(_input("something_unmapped"))

    assert outcome.rule_id == "unclassified"
    assert outcome.requires_clinician_review is True


def test_risk_rules_are_configuration_driven(
    db_session: Session, config: ConfigService, make_user
) -> None:
    """Editing configuration must change the outcome — no hardcoded thresholds."""
    admin = make_user("rules@example.com", RoleName.ADMIN)
    before = RiskEngine(db_session).evaluate(_input(ScreeningCategory.MILD.value))
    assert before.risk_level == RiskLevel.LOW.value

    rules = copy.deepcopy(config.get(KEY_RISK_RULES))
    for rule in rules["rules"]:
        if rule["id"] == "mild-low":
            rule["risk_level"] = RiskLevel.HIGH.value
    config.set(KEY_RISK_RULES, rules, actor=admin)

    after = RiskEngine(db_session).evaluate(_input(ScreeningCategory.MILD.value))
    assert after.risk_level == RiskLevel.HIGH.value


def test_outcome_records_which_rule_fired(
    db_session: Session, config: ConfigService
) -> None:
    outcome = RiskEngine(db_session).evaluate(_input(ScreeningCategory.SEVERE.value))

    assert outcome.rule_id == "severe-high"
    assert outcome.rules_snapshot["matched_rule"]["id"] == "severe-high"


# --------------------------------------------------------------------------- #
# Referral engine
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("risk", "priority", "creates"),
    [
        (RiskLevel.URGENT.value, ReferralPriority.URGENT.value, True),
        (RiskLevel.HIGH.value, ReferralPriority.CONSULTATION.value, True),
        (RiskLevel.MODERATE.value, ReferralPriority.CONSULTATION.value, True),
        (RiskLevel.LOW.value, ReferralPriority.ROUTINE.value, False),
    ],
)
def test_risk_band_drives_referral_priority(
    db_session: Session, config: ConfigService, risk: str, priority: str, creates: bool
) -> None:
    decision = ReferralEngine(db_session).decide(risk_level=risk)

    assert decision.priority == priority
    assert decision.should_create_referral is creates


def test_follow_up_date_reflects_urgency(
    db_session: Session, config: ConfigService
) -> None:
    today = date(2026, 1, 1)
    urgent = ReferralEngine(db_session).decide(
        risk_level=RiskLevel.URGENT.value, today=today
    )
    routine = ReferralEngine(db_session).decide(
        risk_level=RiskLevel.LOW.value, today=today
    )

    assert urgent.follow_up_due < routine.follow_up_due
    assert urgent.follow_up_due > today


def test_unknown_risk_band_is_handled_conservatively(
    db_session: Session, config: ConfigService
) -> None:
    decision = ReferralEngine(db_session).decide(risk_level="not_a_band")

    assert decision.should_create_referral is True
    assert decision.priority == ReferralPriority.CONSULTATION.value


def test_referral_routes_to_a_doctor_at_the_originating_clinic(
    db_session: Session, config: ConfigService, make_user
) -> None:
    from app.models.organization import Clinic, Doctor

    clinic = Clinic(name="Test PHC", code="TEST-PHC")
    db_session.add(clinic)
    db_session.flush()
    user = make_user("routed@example.com", RoleName.DOCTOR)
    db_session.add(Doctor(user_id=user.id, clinic_id=clinic.id))
    db_session.commit()

    decision = ReferralEngine(db_session).decide(
        risk_level=RiskLevel.URGENT.value, origin_clinic_id=clinic.id
    )

    assert decision.routed_clinic_id == clinic.id
    assert decision.routed_doctor_id is not None


def test_referral_is_left_unassigned_when_no_doctor_is_available(
    db_session: Session, config: ConfigService
) -> None:
    """Never invent a destination — an unassigned referral goes to the queue."""
    decision = ReferralEngine(db_session).decide(risk_level=RiskLevel.URGENT.value)

    assert decision.routed_doctor_id is None
