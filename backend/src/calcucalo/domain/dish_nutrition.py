"""Shared dish-nutrition arithmetic.

``POST /api/v1/food/analyze`` and ``POST /api/v1/meals`` must scale a recipe to a
portion with exactly the same rounding. If they do not, the calories shown after
a scan differ from the calories stored in the diary. Keeping the arithmetic in
one place makes that impossible.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

NUTRIENT_KEYS: tuple[str, ...] = ("calories_kcal", "protein_g", "fat_g", "carb_g")

# Mirrors the ``quantity`` bounds accepted by ``MealCreateRequest``.
MAX_QUANTITY = 100.0


class PortionOutOfRangeError(ValueError):
    """Raised when a portion implies an unreasonable number of servings."""


def clean_number(value: float, ndigits: int = 1) -> int | float:
    rounded = round(float(value), ndigits)
    return int(rounded) if rounded.is_integer() else rounded


def quantity_for_portion(portion_g: float, base_portion_g: float) -> float:
    """Return the serving multiplier for a physical portion.

    The value is rounded to 4 decimals so a 55.8 g portion of a 100 g recipe
    becomes ``0.558`` instead of an unbounded float.
    """
    base = float(base_portion_g)
    if base <= 0:
        raise PortionOutOfRangeError("Dish base portion must be positive")
    quantity = round(max(float(portion_g), 1.0) / base, 4)
    if quantity <= 0 or quantity > MAX_QUANTITY:
        raise PortionOutOfRangeError(
            f"Portion {float(portion_g):.1f} g implies {quantity:g} servings; "
            f"the maximum is {MAX_QUANTITY:g}"
        )
    return quantity


def compute_dish_nutrition(
    components: Iterable[Mapping[str, Any]],
    *,
    portion_g: float | None,
    base_portion_g: float,
) -> dict[str, Any]:
    """Scale a recipe's ingredient list to ``portion_g``.

    ``components`` items must expose ``ingredient_id``, ``name``, ``default_g``,
    ``cal_per_100g``, ``protein``, ``fat`` and ``carb`` (the last four are
    per-100-g values).
    """
    base = float(base_portion_g)
    if base <= 0:
        raise PortionOutOfRangeError("Dish base portion must be positive")
    estimated_portion = base if portion_g is None else max(float(portion_g), 1.0)
    portion_scale = estimated_portion / base

    public_components: list[dict[str, Any]] = []
    component_estimates: list[dict[str, Any]] = []
    totals = {key: 0.0 for key in NUTRIENT_KEYS}

    for component in components:
        public = {
            "name": str(component["name"]),
            "default_g": clean_number(float(component["default_g"])),
            "cal_per_100g": clean_number(float(component["cal_per_100g"])),
            "protein": round(float(component["protein"]), 1),
            "fat": round(float(component["fat"]), 1),
            "carb": round(float(component["carb"]), 1),
        }
        public_components.append(public)

        component_weight = float(component["default_g"]) * portion_scale
        factor = component_weight / 100.0
        calculated_nutrients = {
            "calories_kcal": float(public["cal_per_100g"]) * factor,
            "protein_g": float(public["protein"]) * factor,
            "fat_g": float(public["fat"]) * factor,
            "carb_g": float(public["carb"]) * factor,
        }
        estimate = {
            "ingredient_id": str(component["ingredient_id"]),
            "name": public["name"],
            "estimated_g": round(component_weight, 1),
            **{key: round(value, 1) for key, value in calculated_nutrients.items()},
            "basis": "catalog_prior",
            "calculation": {
                "model": "per_100g_nutrition_scaling",
                "formula": "nutrient_amount = nutrient_per_100g * estimated_g / 100",
                "inputs": {
                    "estimated_g": round(component_weight, 6),
                    "cal_per_100g": round(float(public["cal_per_100g"]), 6),
                    "protein_per_100g": round(float(public["protein"]), 6),
                    "fat_per_100g": round(float(public["fat"]), 6),
                    "carb_per_100g": round(float(public["carb"]), 6),
                    "component_weight_basis": "catalog_prior",
                },
                "intermediate": {"portion_factor": round(factor, 8)},
                "outputs": {
                    key: round(value, 6) for key, value in calculated_nutrients.items()
                },
            },
        }
        component_estimates.append(estimate)
        for nutrient in NUTRIENT_KEYS:
            totals[nutrient] += float(estimate[nutrient])

    return {
        "base_portion_g": clean_number(base),
        "estimated_portion_g": round(estimated_portion, 1),
        "portion_scale": round(portion_scale, 6),
        "suggested_quantity": round(portion_scale, 4),
        "components": public_components,
        "estimated_components": component_estimates,
        "estimated_totals": {key: round(value, 1) for key, value in totals.items()},
    }
