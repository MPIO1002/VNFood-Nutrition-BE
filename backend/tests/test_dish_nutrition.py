from __future__ import annotations

import pytest

from calcucalo.domain.dish_nutrition import (
    PortionOutOfRangeError,
    compute_dish_nutrition,
    quantity_for_portion,
)

# Dish 7 in the production database: "Bánh tráng trộn".
DISH_7 = [
    {
        "ingredient_id": "1",
        "name": "Bánh đa nem",
        "default_g": 40.0,
        "cal_per_100g": 333.0,
        "protein": 4.0,
        "fat": 0.2,
        "carb": 78.9,
    },
    {
        "ingredient_id": "2",
        "name": "Hành lá (hành hoa)",
        "default_g": 10.0,
        "cal_per_100g": 22.0,
        "protein": 1.3,
        "fat": 0.0,
        "carb": 4.3,
    },
    {
        "ingredient_id": "3",
        "name": "Thịt bò khô",
        "default_g": 20.0,
        "cal_per_100g": 239.0,
        "protein": 51.0,
        "fat": 1.6,
        "carb": 5.2,
    },
    {
        "ingredient_id": "4",
        "name": "Trứng chim cút",
        "default_g": 30.0,
        "cal_per_100g": 154.0,
        "protein": 13.1,
        "fat": 11.1,
        "carb": 0.4,
    },
]


def test_estimated_portion_matches_analyze_numbers() -> None:
    """A 55.8 g scan portion must save the same 128 kcal the scanner showed."""
    result = compute_dish_nutrition(DISH_7, portion_g=55.8, base_portion_g=100.0)

    assert result["estimated_totals"] == {
        "calories_kcal": 128.0,
        "protein_g": 8.9,
        "fat_g": 2.1,
        "carb_g": 18.5,
    }
    assert result["estimated_portion_g"] == 55.8
    assert result["suggested_quantity"] == 0.558


def test_base_portion_reproduces_catalog_serving() -> None:
    result = compute_dish_nutrition(DISH_7, portion_g=None, base_portion_g=100.0)

    assert result["estimated_totals"] == {
        "calories_kcal": 229.4,
        "protein_g": 15.8,
        "fat_g": 3.7,
        "carb_g": 33.1,
    }
    assert result["suggested_quantity"] == 1.0


def test_totals_are_internally_consistent_with_macros() -> None:
    for portion_g in (55.8, 100.0, 250.0):
        totals = compute_dish_nutrition(
            DISH_7, portion_g=portion_g, base_portion_g=100.0
        )["estimated_totals"]
        macro_kcal = (
            4.0 * totals["protein_g"]
            + 4.0 * totals["carb_g"]
            + 9.0 * totals["fat_g"]
        )
        assert macro_kcal == pytest.approx(totals["calories_kcal"], rel=0.02)


def test_component_weights_scale_with_the_portion() -> None:
    result = compute_dish_nutrition(DISH_7, portion_g=55.8, base_portion_g=100.0)

    first = result["estimated_components"][0]
    assert first["estimated_g"] == 22.3
    assert first["calories_kcal"] == 74.3


def test_quantity_for_portion_rounds_to_four_decimals() -> None:
    assert quantity_for_portion(55.8, 100.0) == 0.558
    assert quantity_for_portion(100.0, 100.0) == 1.0
    assert quantity_for_portion(0.2, 100.0) == 0.01


def test_quantity_for_portion_rejects_invalid_values() -> None:
    with pytest.raises(PortionOutOfRangeError):
        quantity_for_portion(50.0, 0.0)
    with pytest.raises(PortionOutOfRangeError):
        quantity_for_portion(100_000.0, 10.0)
