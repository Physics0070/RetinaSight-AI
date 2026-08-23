"""Initial values for runtime-editable clinical/business configuration.

These are **seed defaults only**. At runtime the ``system_configuration`` table
is the source of truth: an administrator edits thresholds and rules through
``/api/v1/config`` and every change is audited. Nothing in the engines reads
these constants directly — they read the config service.

They live in version control so the starting policy is reviewable and diffable,
never buried as magic numbers inside an algorithm.

IMPORTANT: these starting values are engineering defaults for a system whose
model is not yet trained or clinically validated. They are not derived from a
clinical study and must be reviewed by a qualified clinician before any real use.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import ReferralPriority, RiskLevel, ScreeningCategory

# --- configuration keys (referenced by services; never re-typed as literals) ---
KEY_QUALITY_THRESHOLDS = "quality.thresholds"
KEY_QUALITY_NORMALISATION = "quality.normalisation"
KEY_RISK_RULES = "risk.rules"
KEY_REFERRAL_RULES = "referral.rules"
KEY_SCREENING_CATEGORIES = "screening.categories"
KEY_INFERENCE_POLICY = "inference.policy"


DEFAULT_CONFIGURATION: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------ #
    KEY_QUALITY_THRESHOLDS: {
        "category": "quality_gate",
        "description": (
            "Minimum per-dimension scores (0-1) an image must reach to be passed "
            "to AI screening. Raising these means more retakes but cleaner input."
        ),
        "value": {
            "overall_min": 0.55,
            "blur_min": 0.45,
            "lighting_min": 0.40,
            "framing_min": 0.40,
            "retinal_visibility_min": 0.50,
            "min_width": 224,
            "min_height": 224,
        },
    },
    # ------------------------------------------------------------------ #
    KEY_QUALITY_NORMALISATION: {
        "category": "quality_gate",
        "description": (
            "Reference values that map raw image measurements onto 0-1 scores. "
            "Tune per camera/lens hardware."
        ),
        "value": {
            # Laplacian variance at/above this is considered fully sharp.
            "sharpness_reference": 220.0,
            # Ideal mean luminance (0-255) and the tolerated spread around it.
            "target_luminance": 118.0,
            "luminance_tolerance": 62.0,
            # Fraction of pixels allowed to be clipped black/white.
            "max_clipped_fraction": 0.12,
            # Expected fraction of the frame occupied by the retinal disc.
            "target_coverage": 0.42,
            "coverage_tolerance": 0.30,
            # Max centre offset (fraction of image diagonal) before framing suffers.
            "max_centre_offset": 0.28,
        },
    },
    # ------------------------------------------------------------------ #
    KEY_SCREENING_CATEGORIES: {
        "category": "screening",
        "description": "The five-class DR grading scale and its patient-facing wording.",
        "value": {
            "order": [c.value for c in ScreeningCategory],
            "labels": {
                ScreeningCategory.NO_DR.value: {
                    "clinical": "No diabetic retinopathy detected",
                    "patient": "No signs were found in this screening",
                },
                ScreeningCategory.MILD.value: {
                    "clinical": "Mild non-proliferative DR",
                    "patient": "Early signs were found",
                },
                ScreeningCategory.MODERATE.value: {
                    "clinical": "Moderate non-proliferative DR",
                    "patient": "Some changes were found",
                },
                ScreeningCategory.SEVERE.value: {
                    "clinical": "Severe non-proliferative DR",
                    "patient": "Significant changes were found",
                },
                ScreeningCategory.PROLIFERATIVE.value: {
                    "clinical": "Proliferative DR",
                    "patient": "Advanced changes were found",
                },
            },
        },
    },
    # ------------------------------------------------------------------ #
    KEY_INFERENCE_POLICY: {
        "category": "ai",
        "description": (
            "How AI output is treated. A screening below the confidence floor is "
            "escalated for clinician review regardless of predicted category."
        ),
        "value": {
            "low_confidence_threshold": 0.60,
            "low_confidence_risk_floor": RiskLevel.MODERATE.value,
            # Clinician review is mandatory for every screening in this product.
            "always_require_clinician_review": True,
        },
    },
    # ------------------------------------------------------------------ #
    KEY_RISK_RULES: {
        "category": "risk_engine",
        "description": (
            "Ordered rules mapping a screening result to a risk band. The first "
            "matching rule wins; 'default' applies when nothing matches."
        ),
        "value": {
            "rules": [
                {
                    "id": "quality-insufficient",
                    "when": {"quality_acceptable": False},
                    "risk_level": RiskLevel.MODERATE.value,
                    "reason": "Image quality was insufficient for reliable screening.",
                    "recommended_action": "Repeat the screening with a better capture.",
                    "requires_clinician_review": True,
                },
                {
                    "id": "proliferative-urgent",
                    "when": {"categories": [ScreeningCategory.PROLIFERATIVE.value]},
                    "risk_level": RiskLevel.URGENT.value,
                    "reason": "Screening suggests advanced retinopathy.",
                    "recommended_action": "Urgent ophthalmology referral.",
                    "requires_clinician_review": True,
                },
                {
                    "id": "severe-high",
                    "when": {"categories": [ScreeningCategory.SEVERE.value]},
                    "risk_level": RiskLevel.HIGH.value,
                    "reason": "Screening suggests severe non-proliferative changes.",
                    "recommended_action": "Prompt specialist consultation.",
                    "requires_clinician_review": True,
                },
                {
                    "id": "moderate-moderate",
                    "when": {"categories": [ScreeningCategory.MODERATE.value]},
                    "risk_level": RiskLevel.MODERATE.value,
                    "reason": "Screening suggests moderate changes.",
                    "recommended_action": "Specialist consultation.",
                    "requires_clinician_review": True,
                },
                {
                    "id": "mild-low",
                    "when": {"categories": [ScreeningCategory.MILD.value]},
                    "risk_level": RiskLevel.LOW.value,
                    "reason": "Screening suggests early changes.",
                    "recommended_action": "Routine monitoring.",
                    "requires_clinician_review": True,
                },
                {
                    "id": "no-dr-low",
                    "when": {"categories": [ScreeningCategory.NO_DR.value]},
                    "risk_level": RiskLevel.LOW.value,
                    "reason": "No retinopathy indicated by this screening.",
                    "recommended_action": "Routine monitoring.",
                    "requires_clinician_review": True,
                },
            ],
            "default": {
                "id": "unclassified",
                "risk_level": RiskLevel.MODERATE.value,
                "reason": "The screening result could not be classified confidently.",
                "recommended_action": "Clinician review required.",
                "requires_clinician_review": True,
            },
        },
    },
    # ------------------------------------------------------------------ #
    KEY_REFERRAL_RULES: {
        "category": "referral_engine",
        "description": "Maps a risk band to referral priority, timeframe and wording.",
        "value": {
            "by_risk_level": {
                RiskLevel.URGENT.value: {
                    "priority": ReferralPriority.URGENT.value,
                    "target_days": 7,
                    "action": "Urgent ophthalmology referral",
                    "create_referral": True,
                },
                RiskLevel.HIGH.value: {
                    "priority": ReferralPriority.CONSULTATION.value,
                    "target_days": 30,
                    "action": "Specialist consultation",
                    "create_referral": True,
                },
                RiskLevel.MODERATE.value: {
                    "priority": ReferralPriority.CONSULTATION.value,
                    "target_days": 90,
                    "action": "Specialist consultation",
                    "create_referral": True,
                },
                RiskLevel.LOW.value: {
                    "priority": ReferralPriority.ROUTINE.value,
                    "target_days": 365,
                    "action": "Routine monitoring",
                    "create_referral": False,
                },
            },
            "follow_up_days_by_risk": {
                RiskLevel.URGENT.value: 7,
                RiskLevel.HIGH.value: 30,
                RiskLevel.MODERATE.value: 90,
                RiskLevel.LOW.value: 365,
            },
        },
    },
}
