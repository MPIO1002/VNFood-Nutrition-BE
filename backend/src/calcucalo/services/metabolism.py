from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
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
    current_weight_kg: float
    weight_change_kg: float
    target_weight_kg: float
    current_bmi: float
    target_bmi: float
    bmi_category_general: str
    bmi_category_asian: str
    estimated_rmr_kcal_per_day: float
    activity_factor: float
    estimated_tdee_kcal_per_day: float
    goal_pace: str | None
    requested_goal_adjustment_kcal: float
    applied_goal_adjustment_kcal: float
    daily_calorie_adjustment: float
    minimum_target_kcal: float
    target_was_safety_limited: bool
    target_kcal_per_day: float
    target_protein_g: float
    target_carb_g: float
    target_fat_g: float
    weekly_pace_kg: float | None
    estimated_days: int | None
    estimated_weeks: float | None
    target_date: str | None
    summary_message: str
    formula_name: str
    is_estimate: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


def calculate_macro_targets(
    target_kcal_per_day: float,
    goal: str | None = None,
) -> tuple[float, float, float]:
    """Calculate target protein, carb, and fat in grams based on calorie target and goal."""
    if goal == "lose_weight":
        # Higher protein for satiety and muscle sparing: 35% Protein, 40% Carb, 25% Fat
        p_ratio, c_ratio, f_ratio = 0.35, 0.40, 0.25
    elif goal == "gain_weight":
        # Higher carb for training fuel: 25% Protein, 55% Carb, 20% Fat
        p_ratio, c_ratio, f_ratio = 0.25, 0.55, 0.20
    else:
        # Balanced: 25% Protein, 50% Carb, 25% Fat
        p_ratio, c_ratio, f_ratio = 0.25, 0.50, 0.25

    protein_g = round((target_kcal_per_day * p_ratio) / 4.0, 1)
    carb_g = round((target_kcal_per_day * c_ratio) / 4.0, 1)
    fat_g = round((target_kcal_per_day * f_ratio) / 9.0, 1)
    return protein_g, carb_g, fat_g


def calculate_metabolism(
    *,
    sex_for_equation: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
    goal_pace: str | None = None,
    weight_change_kg: float | None = None,
    pregnant_or_breastfeeding: bool = False,
    competitive_athlete: bool = False,
    metabolism_affecting_condition: bool = False,
) -> MetabolismResult:
    """Estimate adult BMI, resting energy expenditure, TDEE, macro target and timeline.

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

    current_weight = round(float(weight_kg), 1)
    resolved_weight_change = round(float(weight_change_kg), 1) if weight_change_kg is not None else 0.0
    if resolved_weight_change < 0:
        raise ValueError("weight_change_kg must be non-negative")

    if goal == "maintain_weight":
        target_weight = current_weight
        resolved_weight_change = 0.0
    elif goal == "lose_weight":
        target_weight = round(current_weight - resolved_weight_change, 1)
        if target_weight <= 20.0:
            raise UnsafeCalorieTargetError("Cân nặng mục tiêu quá thấp, không an toàn.")
        target_bmi_val = target_weight / ((height_cm / 100.0) ** 2)
        if target_bmi_val < 18.5 and resolved_weight_change > 0:
            raise UnsafeCalorieTargetError(
                f"Mục tiêu giảm {resolved_weight_change:g} kg sẽ khiến BMI đạt {target_bmi_val:.1f} (dưới ngưỡng an toàn 18.5)."
            )
    elif goal == "gain_weight":
        target_weight = round(current_weight + resolved_weight_change, 1)
    else:
        target_weight = current_weight

    displayed_target_bmi = round(target_weight / ((height_cm / 100.0) ** 2), 1)

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
    target_protein_g, target_carb_g, target_fat_g = calculate_macro_targets(target, goal)

    if goal == "maintain_weight":
        weekly_pace = 0.0
        estimated_days = 0
        estimated_weeks = 0.0
        target_date = None
        summary_msg = f"Để duy trì vóc dáng {current_weight:g} kg, bạn nên nạp {target:,.0f} kcal/ngày."
    elif resolved_weight_change == 0.0:
        weekly_pace = 0.5 if resolved_goal_pace == "standard" else 0.25
        estimated_days = None
        estimated_weeks = None
        target_date = None
        verb = "giảm" if goal == "lose_weight" else "tăng"
        summary_msg = f"Mục tiêu {verb} cân an toàn của bạn là {target:,.0f} kcal/ngày."
    else:
        weekly_pace = 0.5 if resolved_goal_pace == "standard" else 0.25
        total_energy_needed = resolved_weight_change * 7700.0
        daily_adj = abs(applied_adjustment)
        if daily_adj > 0:
            estimated_days = int(round(total_energy_needed / daily_adj))
            estimated_weeks = round(estimated_days / 7.0, 1)
            target_date_obj = date.today() + timedelta(days=estimated_days)
            target_date = target_date_obj.isoformat()
            target_date_str = target_date_obj.strftime("%d/%m/%Y")
            verb = "giảm" if goal == "lose_weight" else "tăng"
            summary_msg = (
                f"Để {verb} {resolved_weight_change:g} kg an toàn, bạn nên nạp {target:,.0f} kcal/ngày. "
                f"Bạn dự kiến sẽ đạt {target_weight:g} kg sau khoảng {estimated_weeks:g} tuần (vào ngày {target_date_str})."
            )
        else:
            estimated_days = None
            estimated_weeks = None
            target_date = None
            summary_msg = f"Mục tiêu năng lượng mỗi ngày là {target:,.0f} kcal/ngày."

    return MetabolismResult(
        bmi=displayed_bmi,
        current_weight_kg=current_weight,
        weight_change_kg=resolved_weight_change,
        target_weight_kg=target_weight,
        current_bmi=displayed_bmi,
        target_bmi=displayed_target_bmi,
        bmi_category_general=_bmi_category_general(displayed_bmi),
        bmi_category_asian=_bmi_category_asian(displayed_bmi),
        estimated_rmr_kcal_per_day=float(displayed_rmr),
        activity_factor=activity_factor,
        estimated_tdee_kcal_per_day=float(displayed_tdee),
        goal_pace=resolved_goal_pace,
        requested_goal_adjustment_kcal=requested_adjustment,
        applied_goal_adjustment_kcal=applied_adjustment,
        daily_calorie_adjustment=applied_adjustment,
        minimum_target_kcal=minimum_target,
        target_was_safety_limited=target_was_safety_limited,
        target_kcal_per_day=target,
        target_protein_g=target_protein_g,
        target_carb_g=target_carb_g,
        target_fat_g=target_fat_g,
        weekly_pace_kg=weekly_pace,
        estimated_days=estimated_days,
        estimated_weeks=estimated_weeks,
        target_date=target_date,
        summary_message=summary_msg,
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
