"""Risk engine.

Turns a screening result into a risk band by evaluating the **configured**
rule list — no threshold or category mapping is written into this code. Rules
are ordered; the first match wins.

The engine is deliberately separate from the referral engine: risk is a
clinical judgement about the patient, referral is an operational decision about
what happens next.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.config_defaults import KEY_INFERENCE_POLICY, KEY_RISK_RULES
from app.domain.enums import RiskLevel
from app.services.config_service import ConfigService

logger = get_logger(__name__)

# Ordering used to apply a risk *floor* (never to decide a band outright).
_SEVERITY_ORDER = [
    RiskLevel.LOW.value,
    RiskLevel.MODERATE.value,
    RiskLevel.HIGH.value,
    RiskLevel.URGENT.value,
]


@dataclass
class RiskInput:
    category: str | None
    confidence: float | None
    quality_acceptable: bool
    is_development_model: bool = False
    patient_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskOutcome:
    risk_level: str
    reason: str
    recommended_action: str
    requires_clinician_review: bool
    rule_id: str
    rules_snapshot: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class RiskEngine:
    def __init__(self, db: Session) -> None:
        self.config = ConfigService(db)

    # ------------------------------------------------------------------ #
    def evaluate(self, data: RiskInput) -> RiskOutcome:
        rules_config = self.config.get(KEY_RISK_RULES)
        policy = self.config.get(KEY_INFERENCE_POLICY)

        rules: list[dict] = rules_config.get("rules", [])
        default_rule: dict = rules_config.get("default", {})

        matched = next((r for r in rules if self._matches(r.get("when", {}), data)), None)
        rule = matched or default_rule
        notes: list[str] = []
        if matched is None:
            notes.append("No configured rule matched; the default rule was applied.")

        risk_level = str(rule.get("risk_level", RiskLevel.MODERATE.value))
        reason = str(rule.get("reason", ""))
        action = str(rule.get("recommended_action", ""))
        requires_review = bool(rule.get("requires_clinician_review", True))

        # A low-confidence result cannot sit below the configured floor.
        threshold = float(policy.get("low_confidence_threshold", 0.6))
        if data.confidence is not None and data.confidence < threshold:
            floor = str(policy.get("low_confidence_risk_floor", RiskLevel.MODERATE.value))
            raised = self._apply_floor(risk_level, floor)
            if raised != risk_level:
                notes.append(
                    f"Confidence {data.confidence:.2f} is below {threshold:.2f}; "
                    f"risk raised to the configured floor."
                )
                risk_level = raised
            requires_review = True

        # This product keeps a clinician in the loop by design.
        if bool(policy.get("always_require_clinician_review", True)):
            requires_review = True

        # A placeholder model must never drive an unreviewed clinical outcome.
        if data.is_development_model:
            requires_review = True
            notes.append(
                "Result produced by a development model — not clinically meaningful."
            )

        return RiskOutcome(
            risk_level=risk_level,
            reason=reason,
            recommended_action=action,
            requires_clinician_review=requires_review,
            rule_id=str(rule.get("id", "default")),
            rules_snapshot={
                "matched_rule": rule,
                "low_confidence_threshold": threshold,
            },
            notes=notes,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _matches(condition: dict[str, Any], data: RiskInput) -> bool:
        if "quality_acceptable" in condition:
            if bool(condition["quality_acceptable"]) != data.quality_acceptable:
                return False
        if "categories" in condition:
            if data.category not in list(condition["categories"]):
                return False
        if "min_confidence" in condition:
            if data.confidence is None or data.confidence < float(condition["min_confidence"]):
                return False
        if "max_confidence" in condition:
            if data.confidence is None or data.confidence > float(condition["max_confidence"]):
                return False
        return True

    @staticmethod
    def _apply_floor(current: str, floor: str) -> str:
        try:
            return (
                floor
                if _SEVERITY_ORDER.index(floor) > _SEVERITY_ORDER.index(current)
                else current
            )
        except ValueError:
            logger.warning("Unknown risk level in configuration: %s / %s", current, floor)
            return current
