"""Referral engine.

Decides the operational consequence of a risk band: whether a referral is
raised, at what priority, within what timeframe, and where it is routed.

Kept separate from the risk engine so referral policy (an operational and
capacity question) can change without touching clinical risk logic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domain.config_defaults import KEY_REFERRAL_RULES
from app.domain.enums import ReferralPriority
from app.models.organization import Doctor
from app.services.config_service import ConfigService

logger = get_logger(__name__)


@dataclass
class ReferralDecision:
    should_create_referral: bool
    priority: str
    action: str
    target_days: int
    follow_up_due: date
    routed_clinic_id: uuid.UUID | None = None
    routed_doctor_id: uuid.UUID | None = None
    reason: str = ""
    rules_snapshot: dict[str, Any] = field(default_factory=dict)


class ReferralEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = ConfigService(db)

    def decide(
        self,
        *,
        risk_level: str,
        reason: str = "",
        origin_clinic_id: uuid.UUID | None = None,
        today: date | None = None,
    ) -> ReferralDecision:
        rules = self.config.get(KEY_REFERRAL_RULES)
        by_risk: dict[str, Any] = rules.get("by_risk_level", {})
        follow_up_days: dict[str, Any] = rules.get("follow_up_days_by_risk", {})

        policy = by_risk.get(risk_level)
        if policy is None:
            logger.warning("No referral policy configured for risk level '%s'.", risk_level)
            policy = {
                "priority": ReferralPriority.CONSULTATION.value,
                "target_days": 30,
                "action": "Specialist consultation",
                "create_referral": True,
            }

        reference_day = today or date.today()
        days_to_follow_up = int(follow_up_days.get(risk_level, policy.get("target_days", 90)))

        doctor_id, clinic_id = self._route(origin_clinic_id)

        return ReferralDecision(
            should_create_referral=bool(policy.get("create_referral", True)),
            priority=str(policy.get("priority", ReferralPriority.CONSULTATION.value)),
            action=str(policy.get("action", "")),
            target_days=int(policy.get("target_days", 30)),
            follow_up_due=reference_day + timedelta(days=days_to_follow_up),
            routed_clinic_id=clinic_id,
            routed_doctor_id=doctor_id,
            reason=reason,
            rules_snapshot={"risk_level": risk_level, "policy": policy},
        )

    def _route(
        self, origin_clinic_id: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Prefer a doctor at the originating clinic; otherwise leave unassigned
        for the doctor queue to pick up. Never invents a destination."""
        if origin_clinic_id is not None:
            doctor = self.db.execute(
                select(Doctor).where(Doctor.clinic_id == origin_clinic_id).limit(1)
            ).scalars().first()
            if doctor is not None:
                return doctor.id, origin_clinic_id
        return None, origin_clinic_id
