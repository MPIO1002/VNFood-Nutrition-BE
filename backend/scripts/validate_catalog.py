from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from calcucalo.repositories.nutrition import NutritionCatalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_json_without_duplicates(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def validate(catalog_path: Path, classes_path: Path) -> dict[str, Any]:
    raw = load_json_without_duplicates(catalog_path)
    catalog = NutritionCatalog(catalog_path)
    class_names = yaml.safe_load(classes_path.read_text(encoding="utf-8"))["names"]
    missing_classes = [
        name for class_id, name in class_names.items() if int(class_id) != 27 and not catalog.profile_for(name)
    ]

    food_ids = [str(dish["food_id"]) for dish in raw["dishes"].values()]
    duplicate_food_ids = sorted(
        food_id for food_id, count in Counter(food_ids).items() if count > 1
    )
    energy_warnings: list[dict[str, Any]] = []
    for ingredient_id, ingredient in raw["ingredients"].items():
        stated = float(ingredient["cal_per_100g"])
        from_macros = (
            4.0 * float(ingredient["protein"])
            + 9.0 * float(ingredient["fat"])
            + 4.0 * float(ingredient["carb"])
        )
        delta = abs(stated - from_macros)
        if delta > max(25.0, stated * 0.20):
            energy_warnings.append(
                {
                    "ingredient_id": ingredient_id,
                    "stated_kcal": stated,
                    "macro_formula_kcal": round(from_macros, 1),
                    "delta_kcal": round(delta, 1),
                }
            )

    portion_warnings: list[dict[str, Any]] = []
    for key, dish in raw["dishes"].items():
        base = float(dish["base_portion_g"])
        component_total = sum(float(item["default_g"]) for item in dish["components"])
        difference = base - component_total
        if abs(difference) > max(10.0, base * 0.05):
            portion_warnings.append(
                {
                    "dish": key,
                    "base_portion_g": base,
                    "component_total_g": component_total,
                    "unallocated_g": round(difference, 1),
                }
            )

    return {
        "valid": not missing_classes and not duplicate_food_ids,
        "dish_count": len(raw["dishes"]),
        "ingredient_count": len(raw["ingredients"]),
        "missing_detector_classes": missing_classes,
        "duplicate_food_ids": duplicate_food_ids,
        "energy_consistency_warnings": energy_warnings,
        "portion_allocation_warnings": portion_warnings,
        "note": "Warnings require review but do not necessarily mean invalid data.",
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Validate CalcuCalo nutrition catalog")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=PROJECT_ROOT / "configs" / "food_catalog.json",
    )
    parser.add_argument(
        "--classes",
        type=Path,
        default=PROJECT_ROOT / "configs" / "vietfood67_classes.yaml",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(args.catalog, args.classes)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
