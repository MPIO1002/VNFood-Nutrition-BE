from __future__ import annotations

import pytest

from calcucalo.services.metabolism import calculate_metabolism


def test_mifflin_st_jeor_for_male_maintenance_goal() -> None:
    result = calculate_metabolism(
        gender="male",
        age=30,
        height_cm=175,
        weight_kg=70,
        activity_level="moderate",
        goal="maintain_weight",
    )

    assert result.bmi == 22.9
    assert result.bmi_category == "normal"
    assert result.bmr_kcal_per_day == 1648.8
    assert result.activity_factor == 1.55
    assert result.tdee_kcal_per_day == 2555.6
    assert result.goal_adjustment_kcal == 0
    assert result.target_kcal_per_day == 2555.6


def test_female_weight_loss_applies_500_kcal_adjustment() -> None:
    result = calculate_metabolism(
        gender="female",
        age=28,
        height_cm=160,
        weight_kg=60,
        activity_level="light",
        goal="lose_weight",
    )

    assert result.bmr_kcal_per_day == 1299.0
    assert result.tdee_kcal_per_day == 1786.1
    assert result.goal_adjustment_kcal == -500
    assert result.target_kcal_per_day == 1286.1


def test_calculation_rejects_unknown_activity_level() -> None:
    with pytest.raises(ValueError, match="Unsupported activity level"):
        calculate_metabolism(
            gender="male",
            age=30,
            height_cm=175,
            weight_kg=70,
            activity_level="sometimes",
            goal="maintain_weight",
        )
