from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def normalize_food_name(value: str) -> str:
    """Normalize Vietnamese/English model labels for catalog matching."""
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def clean_number(value: float, ndigits: int = 1) -> int | float:
    rounded = round(float(value), ndigits)
    return int(rounded) if rounded.is_integer() else rounded


@dataclass(frozen=True)
class ComponentEvidence:
    label: str
    weight_g: float
    confidence: float
    method: str
    instance_count: int = 1
    labels: tuple[str, ...] = ()


class NutritionCatalog:
    """Recipe decomposition and per-100-g nutrient lookup.

    The catalog does not claim that hidden ingredients were visually observed. Each
    component is tagged as either ``visual_match`` or ``catalog_prior`` in detailed
    output so callers can expose uncertainty to users.
    """

    REQUIRED_NUTRIENTS = ("cal_per_100g", "protein", "fat", "carb")

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self.path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        self.schema_version = str(payload.get("schema_version", "1.0"))
        self.data_quality = str(payload.get("data_quality", "unknown"))
        self.nutrition_reference = str(payload.get("nutrition_reference", "unspecified"))
        self.ingredients: dict[str, dict[str, Any]] = payload.get("ingredients", {})
        self.dishes: dict[str, dict[str, Any]] = payload.get("dishes", {})
        self._aliases: dict[str, str] = {}
        self._validate_and_index()

    def _validate_and_index(self) -> None:
        food_ids: set[str] = set()
        for key, ingredient in self.ingredients.items():
            for field in ("name", *self.REQUIRED_NUTRIENTS):
                if field not in ingredient:
                    raise ValueError(f"Ingredient '{key}' is missing '{field}'")
            for nutrient in self.REQUIRED_NUTRIENTS:
                if float(ingredient[nutrient]) < 0:
                    raise ValueError(f"Ingredient '{key}' has a negative {nutrient}")

        for key, dish in self.dishes.items():
            for field in ("food_id", "name", "base_portion_g", "components"):
                if field not in dish:
                    raise ValueError(f"Dish '{key}' is missing '{field}'")
            food_id = str(dish["food_id"])
            if food_id in food_ids:
                raise ValueError(f"Duplicate food_id: {food_id}")
            food_ids.add(food_id)
            if float(dish["base_portion_g"]) <= 0:
                raise ValueError(f"Dish '{key}' has an invalid base portion")
            if not dish["components"]:
                raise ValueError(f"Dish '{key}' must have at least one component")
            for component in dish["components"]:
                ingredient_id = component.get("ingredient_id")
                if ingredient_id not in self.ingredients:
                    raise ValueError(
                        f"Dish '{key}' references unknown ingredient '{ingredient_id}'"
                    )
                if float(component.get("default_g", 0)) <= 0:
                    raise ValueError(f"Dish '{key}' contains a non-positive component weight")

            aliases = {key, str(dish["name"]), *map(str, dish.get("aliases", []))}
            for alias in aliases:
                normalized = normalize_food_name(alias)
                previous = self._aliases.get(normalized)
                if previous is not None and previous != key:
                    raise ValueError(f"Catalog alias collision: '{alias}'")
                self._aliases[normalized] = key

    def profile_for(self, label: str) -> dict[str, Any] | None:
        key = self._aliases.get(normalize_food_name(label))
        return self.dishes.get(key) if key is not None else None

    def food_id_for(self, label: str) -> str | None:
        profile = self.profile_for(label)
        return str(profile["food_id"]) if profile else None

    def base_portion_for(self, label: str) -> float | None:
        profile = self.profile_for(label)
        return float(profile["base_portion_g"]) if profile else None

    def is_composite(self, label: str) -> bool:
        profile = self.profile_for(label)
        return bool(profile and len(profile["components"]) > 1)

    def match_component(self, dish_label: str, candidate_label: str) -> str | None:
        profile = self.profile_for(dish_label)
        if profile is None:
            return None
        candidate = normalize_food_name(candidate_label)
        for component in profile["components"]:
            ingredient_id = str(component["ingredient_id"])
            ingredient = self.ingredients[ingredient_id]
            aliases = {
                ingredient_id,
                str(ingredient["name"]),
                *map(str, ingredient.get("aliases", [])),
                *map(str, component.get("detector_labels", [])),
            }
            if candidate in {normalize_food_name(alias) for alias in aliases}:
                return ingredient_id
        return None

    def analyze(
        self,
        label: str,
        *,
        estimated_portion_g: float | None = None,
        portion_method: str | None = None,
        evidence: dict[str, ComponentEvidence] | None = None,
        component_overrides_g: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        profile = self.profile_for(label)
        if profile is None:
            return None
        evidence = evidence or {}
        if component_overrides_g is not None and not isinstance(component_overrides_g, dict):
            raise ValueError("component_overrides_g must be an object")
        try:
            normalized_overrides = {
                normalize_food_name(key): float(value)
                for key, value in (component_overrides_g or {}).items()
            }
        except (TypeError, ValueError) as exc:
            raise ValueError("Every component override must be a numeric gram value") from exc
        applied_override_keys: set[str] = set()
        base_portion = float(profile["base_portion_g"])
        # A generic uncalibrated mass prior is weaker than the recipe-specific base portion.
        if estimated_portion_g is None or portion_method != "mask_area_x_thickness_x_density":
            estimated_portion = base_portion
        else:
            estimated_portion = max(float(estimated_portion_g), 1.0)
        portion_scale = estimated_portion / base_portion

        public_components: list[dict[str, Any]] = []
        component_estimates: list[dict[str, Any]] = []
        totals = {"calories_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0}
        visual_matches = 0
        visual_instances = 0
        for component in profile["components"]:
            ingredient_id = str(component["ingredient_id"])
            ingredient = self.ingredients[ingredient_id]
            public = {
                "name": str(component.get("name", ingredient["name"])),
                "default_g": clean_number(float(component["default_g"])),
                "cal_per_100g": clean_number(float(ingredient["cal_per_100g"])),
                "protein": round(float(ingredient["protein"]), 1),
                "fat": round(float(ingredient["fat"]), 1),
                "carb": round(float(ingredient["carb"]), 1),
            }
            public_components.append(public)

            matched = evidence.get(ingredient_id)
            override_keys = {
                normalize_food_name(ingredient_id),
                normalize_food_name(str(ingredient["name"])),
                normalize_food_name(str(public["name"])),
            }
            override_matches = {
                key: normalized_overrides[key] for key in override_keys if key in normalized_overrides
            }
            if override_matches:
                if len(set(override_matches.values())) > 1:
                    raise ValueError(f"Conflicting overrides for {public['name']}")
                component_weight = next(iter(override_matches.values()))
                if component_weight <= 0:
                    raise ValueError(f"Component override for {public['name']} must be positive")
                basis = "user_override"
                applied_override_keys.update(override_matches)
            elif matched and matched.method == "mask_area_x_thickness_x_density":
                component_weight = matched.weight_g
                basis = "visual_metric_estimate"
                visual_matches += 1
            else:
                component_weight = float(component["default_g"]) * portion_scale
                basis = "visual_match" if matched else "catalog_prior"
                visual_matches += int(matched is not None)

            factor = component_weight / 100.0
            calculated_nutrients = {
                "calories_kcal": float(public["cal_per_100g"]) * factor,
                "protein_g": float(public["protein"]) * factor,
                "fat_g": float(public["fat"]) * factor,
                "carb_g": float(public["carb"]) * factor,
            }
            estimate = {
                "ingredient_id": ingredient_id,
                "name": public["name"],
                "estimated_g": round(component_weight, 1),
                **{key: round(value, 1) for key, value in calculated_nutrients.items()},
                "basis": basis,
                "calculation": {
                    "model": "per_100g_nutrition_scaling",
                    "formula": "nutrient_amount = nutrient_per_100g * estimated_g / 100",
                    "inputs": {
                        "estimated_g": round(component_weight, 6),
                        "cal_per_100g": round(float(public["cal_per_100g"]), 6),
                        "protein_per_100g": round(float(public["protein"]), 6),
                        "fat_per_100g": round(float(public["fat"]), 6),
                        "carb_per_100g": round(float(public["carb"]), 6),
                        "component_weight_basis": basis,
                    },
                    "intermediate": {"portion_factor": round(factor, 8)},
                    "outputs": {
                        key: round(value, 6) for key, value in calculated_nutrients.items()
                    },
                },
            }
            if matched:
                estimate["visual_label"] = matched.label
                estimate["visual_confidence"] = round(matched.confidence, 3)
                estimate["visual_instance_count"] = matched.instance_count
                estimate["visual_labels"] = list(matched.labels or (matched.label,))
                visual_instances += matched.instance_count
            component_estimates.append(estimate)
            for nutrient in totals:
                totals[nutrient] += float(estimate[nutrient])

        rounded_totals = {key: round(value, 1) for key, value in totals.items()}
        return {
            "food_id": str(profile["food_id"]),
            "name": str(profile["name"]),
            "base_portion_g": clean_number(base_portion),
            "components": public_components,
            "estimated_portion_g": round(estimated_portion, 1),
            "estimated_components": component_estimates,
            "estimated_totals": rounded_totals,
            "total_calculation": {
                "model": "sum_component_nutrients",
                "formula": "dish_total = sum(component_nutrient_amounts)",
                "component_count": len(component_estimates),
                "outputs": rounded_totals,
            },
            "analysis_basis": (
                "visual_components_plus_recipe_catalog"
                if visual_matches
                else "dish_detection_plus_recipe_catalog"
            ),
            "visual_components_matched": visual_matches,
            "visual_instances_matched": visual_instances,
            "user_components_overridden": len(applied_override_keys),
            "unmatched_component_overrides": sorted(
                set(normalized_overrides) - applied_override_keys
            ),
            "data_quality": str(profile.get("data_quality", self.data_quality)),
            "nutrition_reference": self.nutrition_reference,
            "notes": list(map(str, profile.get("notes", []))),
        }

    @staticmethod
    def compact(food: dict[str, Any]) -> dict[str, Any]:
        """Return exactly the stable mobile-facing recipe schema."""
        return {
            "food_id": food["food_id"],
            "name": food["name"],
            "base_portion_g": food["base_portion_g"],
            "components": [
                {
                    key: component[key]
                    for key in ("name", "default_g", "cal_per_100g", "protein", "fat", "carb")
                }
                for component in food["components"]
            ],
        }
