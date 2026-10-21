from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

GOAL_PACE_ADJUSTMENTS_KCAL: dict[str, dict[str, float]] = {
    "gradual": {"lose_weight": -250.0, "gain_weight": 250.0},
    "standard": {"lose_weight": -500.0, "gain_weight": 500.0},
}

SEX_OFFSETS: dict[str, float] = {
    "male": 5.0,
    "female": -161.0,
}

# These are conservative planning floors, not universal prescriptions. When a
# deficit cannot fit above the relevant floor, this service refuses to produce
# a weight-loss target and directs the caller to professional assessment.
WEIGHT_LOSS_FLOORS_KCAL: dict[str, float] = {
    "male": 1500.0,
    "female": 1200.0,
}
ABSOLUTE_MINIMUM_INTAKE_KCAL = 1000.0
MIFFLIN_ST_JEOR_STUDY_MIN_AGE = 19
MIFFLIN_ST_JEOR_STUDY_MAX_AGE = 78


class UnsupportedMetabolismProfileError(ValueError):
    """Raised when the estimator is not appropriate for the supplied profile."""


class UnsafeCalorieTargetError(ValueError):
    """Raised instead of returning a potentially unsafe calorie target."""


@dataclass(frozen=True)
class MetabolismResult:
    bmi: float
    bmi_category_general: str
    bmi_category_asian: str
    estimated_rmr_kcal_per_day: float
    activity_factor: float
    estimated_tdee_kcal_per_day: float
    goal_pace: str | None
    requested_goal_adjustment_kcal: float
    applied_goal_adjustment_kcal: float
    minimum_target_kcal: float
    target_was_safety_limited: bool
    target_kcal_per_day: float
    formula_name: str
    is_estimate: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


def calculate_metabolism(
    *,
    sex_for_equation: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
    goal_pace: str | None = None,
    pregnant_or_breastfeeding: bool = False,
    competitive_athlete: bool = False,
    metabolism_affecting_condition: bool = False,
) -> MetabolismResult:
    """Estimate adult BMI, resting energy expenditure, TDEE and calorie target.

    Resting energy expenditure uses Mifflin-St Jeor. The result is a planning
    estimate for generally healthy adults, not a diagnosis or prescription.
    Unsupported special populations are rejected instead of receiving a
    misleadingly precise result.
    """

    _validate_supported_profile(
        pregnant_or_breastfeeding=pregnant_or_breastfeeding,
        competitive_athlete=competitive_athlete,
        metabolism_affecting_condition=metabolism_affecting_condition,
    )
    try:
        sex_offset = SEX_OFFSETS[sex_for_equation]
    except KeyError as exc:
        raise ValueError(f"Unsupported sex for equation: {sex_for_equation}") from exc
    try:
        activity_factor = ACTIVITY_FACTORS[activity_level]
    except KeyError as exc:
        raise ValueError(f"Unsupported activity level: {activity_level}") from exc

    resolved_goal_pace, requested_adjustment = _goal_adjustment(goal, goal_pace)
    bmi = weight_kg / ((height_cm / 100.0) ** 2)
    if goal == "lose_weight" and bmi < 18.5:
        raise UnsafeCalorieTargetError("Weight-loss target is not available when BMI is below 18.5")

    estimated_rmr = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age + sex_offset
    estimated_tdee = estimated_rmr * activity_factor
    if estimated_rmr <= 0 or estimated_tdee < ABSOLUTE_MINIMUM_INTAKE_KCAL:
        raise UnsupportedMetabolismProfileError(
            "The estimated energy need is outside the supported range; seek professional assessment"
        )

    displayed_rmr = round(estimated_rmr)
    displayed_tdee = round(estimated_tdee)
    displayed_bmi = round(bmi, 1)
    minimum_target = _minimum_target(goal, sex_for_equation)
    if goal == "lose_weight" and displayed_tdee <= minimum_target:
        raise UnsafeCalorieTargetError(
            "A safe calorie deficit cannot be estimated for this profile; "
            "seek professional assessment"
        )

    requested_target = displayed_tdee + requested_adjustment
    target = max(requested_target, minimum_target)
    target_was_safety_limited = target != requested_target
    applied_adjustment = target - displayed_tdee

    warnings = _build_warnings(
        age=age,
        bmi=bmi,
        goal=goal,
        target_was_safety_limited=target_was_safety_limited,
    )
    return MetabolismResult(
        bmi=displayed_bmi,
        bmi_category_general=_bmi_category_general(displayed_bmi),
        bmi_category_asian=_bmi_category_asian(displayed_bmi),
        estimated_rmr_kcal_per_day=float(displayed_rmr),
        activity_factor=activity_factor,
        estimated_tdee_kcal_per_day=float(displayed_tdee),
        goal_pace=resolved_goal_pace,
        requested_goal_adjustment_kcal=requested_adjustment,
        applied_goal_adjustment_kcal=applied_adjustment,
        minimum_target_kcal=minimum_target,
        target_was_safety_limited=target_was_safety_limited,
        target_kcal_per_day=target,
        formula_name="mifflin_st_jeor_1990",
        is_estimate=True,
        warnings=warnings,
    )


def _validate_supported_profile(
    *,
    pregnant_or_breastfeeding: bool,
    competitive_athlete: bool,
    metabolism_affecting_condition: bool,
) -> None:
    unsupported: list[str] = []
    if pregnant_or_breastfeeding:
        unsupported.append("pregnancy or breastfeeding")
    if competitive_athlete:
        unsupported.append("competitive athlete")
    if metabolism_affecting_condition:
        unsupported.append("a condition or medication affecting metabolism")
    if unsupported:
        raise UnsupportedMetabolismProfileError(
            "This estimator is not intended for profiles with " + ", ".join(unsupported)
        )


def _goal_adjustment(goal: str, goal_pace: str | None) -> tuple[str | None, float]:
    if goal == "maintain_weight":
        if goal_pace is not None:
            raise ValueError("goal_pace must be omitted when goal is maintain_weight")
        return None, 0.0
    if goal not in {"lose_weight", "gain_weight"}:
        raise ValueError(f"Unsupported goal: {goal}")

    resolved_pace = goal_pace or "gradual"
    try:
        adjustment = GOAL_PACE_ADJUSTMENTS_KCAL[resolved_pace][goal]
    except KeyError as exc:
        raise ValueError(f"Unsupported goal pace: {resolved_pace}") from exc
    return resolved_pace, adjustment


def _minimum_target(goal: str, sex_for_equation: str) -> float:
    if goal == "lose_weight":
        return WEIGHT_LOSS_FLOORS_KCAL[sex_for_equation]
    return ABSOLUTE_MINIMUM_INTAKE_KCAL


def _build_warnings(
    *, age: int, bmi: float, goal: str, target_was_safety_limited: bool
) -> tuple[str, ...]:
    warnings = [
        "RMR and TDEE are estimates and may differ from measured energy expenditure.",
        "Recalculate after a meaningful weight or activity change.",
    ]
    if not MIFFLIN_ST_JEOR_STUDY_MIN_AGE <= age <= MIFFLIN_ST_JEOR_STUDY_MAX_AGE:
        warnings.append(
            "Age is outside the 19-78 year range in the original Mifflin-St Jeor study."
        )
    if goal == "lose_weight" and bmi < 23.0:
        warnings.append(
            "BMI is below the Asian-population overweight action point; "
            "consider professional guidance before weight loss."
        )
    if target_was_safety_limited:
        warnings.append(
            "The requested calorie deficit was reduced to respect the planning safety floor."
        )
    return tuple(warnings)


def _bmi_category_general(bmi: float) -> str:
    if bmi < 18.5:
        return "underweight"
    if bmi < 25.0:
        return "healthy_weight"
    if bmi < 30.0:
        return "overweight"
    return "obesity"


def _bmi_category_asian(bmi: float) -> str:
    if bmi < 18.5:
        return "underweight"
    if bmi < 23.0:
        return "healthy_weight"
    if bmi < 27.5:
        return "overweight"
    return "obesity"
