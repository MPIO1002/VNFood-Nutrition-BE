from __future__ import annotations

import pytest

from calcucalo.services.metabolism import (
    UnsafeCalorieTargetError,
    UnsupportedMetabolismProfileError,
    calculate_metabolism,
)


def test_mifflin_st_jeor_for_male_maintenance_goal() -> None:
    result = calculate_metabolism(
        sex_for_equation="male",
        age=30,
        height_cm=175,
        weight_kg=70,
        activity_level="moderate",
        goal="maintain_weight",
    )

    assert result.bmi == 22.9
    assert result.bmi_category_general == "healthy_weight"
    assert result.bmi_category_asian == "healthy_weight"
    assert result.estimated_rmr_kcal_per_day == 1649.0
    assert result.activity_factor == 1.55
    assert result.estimated_tdee_kcal_per_day == 2556.0
    assert result.applied_goal_adjustment_kcal == 0
    assert result.target_kcal_per_day == 2556.0
    assert result.goal_pace is None
    assert result.is_estimate is True


def test_weight_loss_defaults_to_gradual_adjustment() -> None:
    result = calculate_metabolism(
        sex_for_equation="female",
        age=28,
        height_cm=160,
        weight_kg=60,
        activity_level="light",
        goal="lose_weight",
    )

    assert result.estimated_rmr_kcal_per_day == 1299.0
    assert result.estimated_tdee_kcal_per_day == 1786.0
    assert result.goal_pace == "gradual"
    assert result.requested_goal_adjustment_kcal == -250
    assert result.applied_goal_adjustment_kcal == -250
    assert result.target_kcal_per_day == 1536.0


def test_standard_weight_loss_is_limited_by_planning_floor() -> None:
    result = calculate_metabolism(
        sex_for_equation="female",
        age=60,
        height_cm=160,
        weight_kg=60,
        activity_level="sedentary",
        goal="lose_weight",
        goal_pace="standard",
    )

    assert result.estimated_tdee_kcal_per_day == 1367.0
    assert result.requested_goal_adjustment_kcal == -500
    assert result.applied_goal_adjustment_kcal == -167
    assert result.minimum_target_kcal == 1200
    assert result.target_kcal_per_day == 1200
    assert result.target_was_safety_limited is True


def test_general_and_asian_bmi_categories_are_both_returned() -> None:
    result = calculate_metabolism(
        sex_for_equation="male",
        age=30,
        height_cm=175,
        weight_kg=73.5,
        activity_level="moderate",
        goal="maintain_weight",
    )

    assert result.bmi == 24.0
    assert result.bmi_category_general == "healthy_weight"
    assert result.bmi_category_asian == "overweight"


def test_bmi_category_matches_the_displayed_rounded_bmi() -> None:
    result = calculate_metabolism(
        sex_for_equation="male",
        age=30,
        height_cm=175,
        weight_kg=76.44,
        activity_level="moderate",
        goal="maintain_weight",
    )

    assert result.bmi == 25.0
    assert result.bmi_category_general == "overweight"


def test_weight_loss_is_rejected_for_underweight_profile() -> None:
    with pytest.raises(UnsafeCalorieTargetError, match="BMI is below 18.5"):
        calculate_metabolism(
            sex_for_equation="female",
            age=30,
            height_cm=170,
            weight_kg=50,
            activity_level="sedentary",
            goal="lose_weight",
        )


def test_out_of_range_energy_estimate_is_rejected_instead_of_returning_negative_target() -> None:
    with pytest.raises(UnsupportedMetabolismProfileError, match="outside the supported range"):
        calculate_metabolism(
            sex_for_equation="female",
            age=120,
            height_cm=101,
            weight_kg=25.1,
            activity_level="sedentary",
            goal="maintain_weight",
        )


def test_special_population_is_rejected() -> None:
    with pytest.raises(UnsupportedMetabolismProfileError, match="pregnancy"):
        calculate_metabolism(
            sex_for_equation="female",
            age=30,
            height_cm=160,
            weight_kg=60,
            activity_level="light",
            goal="maintain_weight",
            pregnant_or_breastfeeding=True,
        )


def test_calculation_rejects_unknown_activity_level() -> None:
    with pytest.raises(ValueError, match="Unsupported activity level"):
        calculate_metabolism(
            sex_for_equation="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="sometimes",
            goal="maintain_weight",
        )
