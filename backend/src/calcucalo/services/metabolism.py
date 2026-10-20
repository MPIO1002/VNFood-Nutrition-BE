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

GOAL_ADJUSTMENTS_KCAL: dict[str, float] = {
    "lose_weight": -500.0,
    "maintain_weight": 0.0,
    "gain_weight": 500.0,
}

GENDER_OFFSETS: dict[str, float] = {
    "male": 5.0,
    "female": -161.0,
}


@dataclass(frozen=True)
class MetabolismResult:
    bmi: float
    bmi_category: str
    bmr_kcal_per_day: float
    activity_factor: float
    tdee_kcal_per_day: float
    goal_adjustment_kcal: float
    target_kcal_per_day: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_metabolism(
    *,
    gender: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity_level: str,
    goal: str,
) -> MetabolismResult:
    """Calculate adult BMI, BMR, TDEE and a daily calorie target.

    BMR uses the Mifflin-St Jeor equation. TDEE multiplies BMR by the selected
    activity factor. The goal target applies a conventional +/-500 kcal/day
    adjustment and is an estimate, not a medical prescription.
    """

    try:
        gender_offset = GENDER_OFFSETS[gender]
    except KeyError as exc:
        raise ValueError(f"Unsupported gender: {gender}") from exc
    try:
        activity_factor = ACTIVITY_FACTORS[activity_level]
    except KeyError as exc:
        raise ValueError(f"Unsupported activity level: {activity_level}") from exc
    try:
        goal_adjustment = GOAL_ADJUSTMENTS_KCAL[goal]
    except KeyError as exc:
        raise ValueError(f"Unsupported goal: {goal}") from exc

    bmi = weight_kg / ((height_cm / 100.0) ** 2)
    bmr = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age + gender_offset
    tdee = bmr * activity_factor
    target = tdee + goal_adjustment

    return MetabolismResult(
        bmi=round(bmi, 1),
        bmi_category=_bmi_category(bmi),
        bmr_kcal_per_day=round(bmr, 1),
        activity_factor=activity_factor,
        tdee_kcal_per_day=round(tdee, 1),
        goal_adjustment_kcal=goal_adjustment,
        target_kcal_per_day=round(target, 1),
    )


def _bmi_category(bmi: float) -> str:
    if bmi < 18.5:
        return "underweight"
    if bmi < 25.0:
        return "normal"
    if bmi < 30.0:
        return "overweight"
    return "obesity"
