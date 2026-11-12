from __future__ import annotations

import json
import logging
import re
import unicodedata

import yaml

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    pass
from pathlib import Path
from typing import Any

from ..domain.dish_nutrition import compute_dish_nutrition


# Detector labels come from the ASCII class list, so a few of them differ from the
# Vietnamese dish names stored in the database. Keys and values are normalized names.
LABEL_ALIASES = {
    "canh kho hoa": "canh kho qua",  # "Canh kho hoa" label vs "Canh khổ qua" dish
    "rau muon xao": "rau muong xao",  # DB typo "Rau muốn xào" vs "Rau muống xào"
}


def normalize_food_name(value: str) -> str:
    """Normalize Vietnamese/English model labels for catalog matching."""
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
    value = unicodedata.normalize("NFKD", value.casefold())
    # "đ" does not decompose under NFKD, so fold it explicitly to keep labels such as
    # "Bún đậu" and "Đậu hũ" matchable against their ASCII class names.
    value = value.replace("đ", "d")
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def canonical_food_key(value: str) -> str:
    """Normalize a label and apply the known label-to-dish alias mapping."""
    normalized = normalize_food_name(value)
    return LABEL_ALIASES.get(normalized, normalized)


def clean_number(value: float, ndigits: int = 1) -> int | float:
    rounded = round(float(value), ndigits)
    return int(rounded) if rounded.is_integer() else rounded



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
                normalized = canonical_food_key(alias)
                previous = self._aliases.get(normalized)
                if previous is not None and previous != key:
                    raise ValueError(f"Catalog alias collision: '{alias}'")
                self._aliases[normalized] = key

    def profile_for(self, label: str) -> dict[str, Any] | None:
        key = self._aliases.get(canonical_food_key(label))
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
        candidate = canonical_food_key(candidate_label)
        for component in profile["components"]:
            ingredient_id = str(component["ingredient_id"])
            ingredient = self.ingredients[ingredient_id]
            aliases = {
                ingredient_id,
                str(ingredient["name"]),
                *map(str, ingredient.get("aliases", [])),
                *map(str, component.get("detector_labels", [])),
            }
            if candidate in {canonical_food_key(alias) for alias in aliases}:
                return ingredient_id
        return None

    def analyze(
        self,
        label: str,
        *,
        estimated_portion_g: float | None = None,
        portion_method: str | None = None,
    ) -> dict[str, Any] | None:
        profile = self.profile_for(label)
        if profile is None:
            return None
        base_portion = float(profile["base_portion_g"])

        components: list[dict[str, Any]] = []
        for component in profile["components"]:
            ingredient_id = str(component["ingredient_id"])
            ingredient = self.ingredients[ingredient_id]
            components.append(
                {
                    "ingredient_id": ingredient_id,
                    "name": str(component.get("name", ingredient["name"])),
                    "default_g": float(component["default_g"]),
                    "cal_per_100g": float(ingredient["cal_per_100g"]),
                    "protein": float(ingredient["protein"]),
                    "fat": float(ingredient["fat"]),
                    "carb": float(ingredient["carb"]),
                }
            )

        nutrition = compute_dish_nutrition(
            components,
            portion_g=estimated_portion_g,
            base_portion_g=base_portion,
        )
        rounded_totals = nutrition["estimated_totals"]
        return {
            "food_id": str(profile["food_id"]),
            "dish_id": None,
            "name": str(profile["name"]),
            "base_portion_g": nutrition["base_portion_g"],
            "components": nutrition["components"],
            "estimated_portion_g": nutrition["estimated_portion_g"],
            "suggested_quantity": nutrition["suggested_quantity"],
            "estimated_components": nutrition["estimated_components"],
            "estimated_totals": rounded_totals,
            "total_calculation": {
                "model": "sum_component_nutrients",
                "formula": "dish_total = sum(component_nutrient_amounts)",
                "component_count": len(nutrition["estimated_components"]),
                "outputs": rounded_totals,
            },
            "analysis_basis": "dish_detection_plus_recipe_catalog",
            "data_quality": str(profile.get("data_quality", self.data_quality)),
            "nutrition_reference": self.nutrition_reference,
            "notes": list(map(str, profile.get("notes", []))),
        }

    @staticmethod
    def compact(food: dict[str, Any]) -> dict[str, Any]:
        """Return the stable mobile-facing recipe schema plus save helpers."""
        return {
            "food_id": food["food_id"],
            "dish_id": food.get("dish_id"),
            "name": food["name"],
            "base_portion_g": food["base_portion_g"],
            "estimated_portion_g": food.get("estimated_portion_g"),
            "suggested_quantity": food.get("suggested_quantity"),
            "components": [
                {
                    key: component[key]
                    for key in ("name", "default_g", "cal_per_100g", "protein", "fat", "carb")
                }
                for component in food["components"]
            ],
        }

class NutritionDB:
    def __init__(self, config_path: str | Path, fallback_catalog: NutritionCatalog | None = None):
        self.config_path = Path(config_path)
        self.fallback_catalog = fallback_catalog
        self.db_config = None
        self._dish_map = {}
        
        import os
        try:
            if self.config_path.exists():
                with self.config_path.open("r", encoding="utf-8") as f:
                    self.db_config = yaml.safe_load(f)
            
            if self.db_config or os.getenv("DATABASE_URL"):
                self._load_dishes()
        except Exception as e:
            logging.warning(f"Could not load DB config or connect: {e}")

    def _get_conn(self):
        import os

        import psycopg2
        env_uri = os.getenv("DATABASE_URL")
        if env_uri:
            return psycopg2.connect(env_uri)
        if self.db_config and "uri" in self.db_config:
            return psycopg2.connect(self.db_config["uri"])
        return psycopg2.connect(
            host=self.db_config["host"],
            port=self.db_config["port"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            database=self.db_config["database"]
        )

    def _load_dishes(self):
        try:
            conn = self._get_conn()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT id, dishes_name FROM dishes")
            for row in cursor.fetchall():
                normalized = canonical_food_key(row["dishes_name"])
                self._dish_map[normalized] = row["dishes_name"]
            conn.close()
        except Exception as e:
            logging.warning(f"DB load dishes failed: {e}")

    def base_portion_for(self, label: str) -> float | None:
        import os
        if (not self.db_config and not os.getenv("DATABASE_URL")) or not self._dish_map:
            return self.fallback_catalog.base_portion_for(label) if self.fallback_catalog else None
            
        normalized_label = canonical_food_key(label)
        db_dish_name = self._dish_map.get(normalized_label)
        
        if not db_dish_name:
            return self.fallback_catalog.base_portion_for(label) if self.fallback_catalog else None

        try:
            import psycopg2
            import psycopg2.extras
            conn = self._get_conn()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
            SELECT SUM(di.quantity) as base_portion 
            FROM dish_ingredients di 
            JOIN dishes d ON di.dish_id = d.id 
            WHERE d.dishes_name = %s
            """
            cursor.execute(query, (db_dish_name,))
            row = cursor.fetchone()
            conn.close()
            if row and row["base_portion"]:
                return float(row["base_portion"])
        except Exception as e:
            import logging
            logging.warning(f"Error getting base portion for {label}: {e}")
            
        return self.fallback_catalog.base_portion_for(label) if self.fallback_catalog else None

    def analyze(
        self,
        label: str,
        *,
        estimated_portion_g: float | None = None,
        portion_method: str | None = None,
    ) -> dict[str, Any] | None:
        import os
        if (not self.db_config and not os.getenv("DATABASE_URL")) or not self._dish_map:
            return self.fallback_catalog.analyze(label, estimated_portion_g=estimated_portion_g, portion_method=portion_method) if self.fallback_catalog else None
            
        normalized_label = canonical_food_key(label)
        db_dish_name = self._dish_map.get(normalized_label)
        
        if not db_dish_name:
            return self.fallback_catalog.analyze(label, estimated_portion_g=estimated_portion_g, portion_method=portion_method) if self.fallback_catalog else None

        try:
            conn = self._get_conn()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Fetch components
            query = """
            SELECT
                d.id AS dish_id,
                d.dishes_name AS dish_name,
                i.id AS ingredient_id,
                i.ingredients_name AS ingredient_name,
                di.quantity AS default_g,
                i.calories AS cal_per_100g,
                i.protein AS protein_per_100g,
                i.fat AS fat_per_100g,
                i.carb AS carb_per_100g
            FROM dishes d
            JOIN dish_ingredients di ON d.id = di.dish_id
            JOIN ingredients i       ON di.ingredient_id = i.id
            WHERE d.dishes_name = %s
            """
            cursor.execute(query, (db_dish_name,))
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return None
                
            base_portion = sum(float(r["default_g"]) for r in rows)
            components = [
                {
                    "ingredient_id": str(r["ingredient_id"]),
                    "name": str(r["ingredient_name"]),
                    "default_g": float(r["default_g"]),
                    "cal_per_100g": float(r["cal_per_100g"]),
                    "protein": float(r["protein_per_100g"]),
                    "fat": float(r["fat_per_100g"]),
                    "carb": float(r["carb_per_100g"]),
                }
                for r in rows
            ]
            nutrition = compute_dish_nutrition(
                components,
                portion_g=estimated_portion_g,
                base_portion_g=base_portion,
            )
            rounded_totals = nutrition["estimated_totals"]
            dish_id = str(rows[0]["dish_id"])
            return {
                "food_id": f"DB_{dish_id}",
                "dish_id": int(rows[0]["dish_id"]),
                "name": db_dish_name,
                "base_portion_g": nutrition["base_portion_g"],
                "components": nutrition["components"],
                "estimated_portion_g": nutrition["estimated_portion_g"],
                "suggested_quantity": nutrition["suggested_quantity"],
                "estimated_components": nutrition["estimated_components"],
                "estimated_totals": rounded_totals,
                "total_calculation": {
                    "model": "sum_component_nutrients",
                    "formula": "dish_total = sum(component_nutrient_amounts)",
                    "component_count": len(nutrition["estimated_components"]),
                    "outputs": rounded_totals,
                },
                "analysis_basis": "dish_detection_plus_recipe_database",
                "data_quality": "database",
                "nutrition_reference": "nutrition_db",
                "notes": ["Fetched from MySQL database"],
            }
        except Exception as e:
            logging.error(f"DB Error for dish {db_dish_name}: {e}")
            return None

    @staticmethod
    def compact(food: dict[str, Any]) -> dict[str, Any]:
        return NutritionCatalog.compact(food)
