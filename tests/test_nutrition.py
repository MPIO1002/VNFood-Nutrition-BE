import json
from pathlib import Path

import numpy as np

from calcucalo.analyzer import FoodImageAnalyzer
from calcucalo.domain import BoundingBox, Detection
from calcucalo.nutrition import NutritionCatalog
from calcucalo.portion import PortionEstimator
from calcucalo.segmenter import BoundingBoxSegmenter

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "configs" / "food_catalog.json"
PRIORS = ROOT / "configs" / "portion_priors.yaml"
CLASSES = ROOT / "configs" / "vietfood67_classes.yaml"


def test_catalog_json_has_no_duplicate_keys() -> None:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    json.loads(CATALOG.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def test_com_tam_compact_schema_matches_requested_contract() -> None:
    catalog = NutritionCatalog(CATALOG)
    food = catalog.analyze("Com tam (Broken rice)")

    assert food is not None
    assert catalog.compact(food) == {
        "food_id": "VN_COM_TAM",
        "name": "Cơm tấm sườn bì chả",
        "base_portion_g": 380,
        "components": [
            {
                "name": "Cơm tấm",
                "default_g": 200,
                "cal_per_100g": 130,
                "protein": 2.7,
                "fat": 0.3,
                "carb": 28.2,
            },
            {
                "name": "Sườn nướng",
                "default_g": 100,
                "cal_per_100g": 240,
                "protein": 20.0,
                "fat": 17.0,
                "carb": 1.0,
            },
            {
                "name": "Chả trứng",
                "default_g": 50,
                "cal_per_100g": 160,
                "protein": 11.0,
                "fat": 11.0,
                "carb": 4.0,
            },
        ],
    }


def test_com_tam_base_nutrition_uses_catalog_scale() -> None:
    catalog = NutritionCatalog(CATALOG)

    food = catalog.analyze("Com tam")

    assert food is not None
    assert food["estimated_components"][0]["basis"] == "catalog_prior"
    assert food["analysis_basis"] == "dish_detection_plus_recipe_catalog"
    assert food["total_calculation"]["component_count"] == 3
    assert food["total_calculation"]["outputs"] == food["estimated_totals"]


def test_catalog_covers_every_food_class_except_human() -> None:
    import yaml

    catalog = NutritionCatalog(CATALOG)
    names = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))["names"]
    missing = [name for class_id, name in names.items() if class_id != 27 and not catalog.profile_for(name)]

    assert missing == []


def test_dish_detections_are_analyzed_with_catalog() -> None:
    class CompositeDetector:
        def predict(self, image_rgb: np.ndarray) -> list[Detection]:
            return [Detection(26, "Com tam", 0.95, BoundingBox(5, 5, 95, 95))]

    analyzer = FoodImageAnalyzer(
        CompositeDetector(),
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
        nutrition_catalog=NutritionCatalog(CATALOG),
    )
    result = analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8))

    food = result.to_dict()["foods"][0]
    assert food["food_id"] == "VN_COM_TAM"
    assert food["analysis_basis"] == "dish_detection_plus_recipe_catalog"
    assert result.to_nutrition_dict(compact=True, unwrap_single=True)["food_id"] == "VN_COM_TAM"
