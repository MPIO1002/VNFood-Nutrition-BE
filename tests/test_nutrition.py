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


def test_user_component_grams_override_catalog_estimate_and_recalculate_macros() -> None:
    catalog = NutritionCatalog(CATALOG)

    food = catalog.analyze(
        "Com tam",
        component_overrides_g={"Cơm tấm": 150, "unknown topping": 25},
    )

    assert food is not None
    assert food["estimated_components"][0]["estimated_g"] == 150
    assert food["estimated_components"][0]["basis"] == "user_override"
    assert food["estimated_components"][0]["calories_kcal"] == 195
    calculation = food["estimated_components"][0]["calculation"]
    assert calculation["inputs"]["estimated_g"] == 150
    assert calculation["intermediate"]["portion_factor"] == 1.5
    assert calculation["outputs"]["calories_kcal"] == 195
    assert food["total_calculation"]["component_count"] == 3
    assert food["total_calculation"]["outputs"] == food["estimated_totals"]
    assert food["user_components_overridden"] == 1
    assert food["unmatched_component_overrides"] == ["unknown topping"]


def test_catalog_covers_every_food_class_except_human() -> None:
    import yaml

    catalog = NutritionCatalog(CATALOG)
    names = yaml.safe_load(CLASSES.read_text(encoding="utf-8"))["names"]
    missing = [name for class_id, name in names.items() if class_id != 27 and not catalog.profile_for(name)]

    assert missing == []


class CompositeDetector:
    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        return [
            Detection(26, "Com tam", 0.95, BoundingBox(5, 5, 95, 95)),
            Detection(25, "Com", 0.90, BoundingBox(10, 40, 55, 90)),
            Detection(54, "Thit nuong", 0.85, BoundingBox(58, 20, 90, 55)),
        ]


def test_nested_visual_detections_are_grouped_as_recipe_components() -> None:
    analyzer = FoodImageAnalyzer(
        CompositeDetector(),
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
        nutrition_catalog=NutritionCatalog(CATALOG),
    )
    result = analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8))

    food = result.to_dict()["foods"][0]
    assert food["food_id"] == "VN_COM_TAM"
    assert food["visual_components_matched"] == 2
    assert food["analysis_basis"] == "visual_components_plus_recipe_catalog"
    assert result.items[1].component_of == "VN_COM_TAM"
    assert result.items[2].component_of == "VN_COM_TAM"
    assert result.items[0].portion.weight_g == 380
    assert result.items[0].portion.method == "recipe_base_portion_prior"
    portion_trace = result.items[0].portion.to_dict()["calculation"]
    assert portion_trace["model"] == "recipe_base_portion_prior"
    assert portion_trace["inputs"]["recipe_base_portion_g"] == 380
    assert portion_trace["outputs"]["estimated_weight_g"] == 380
    assert result.to_nutrition_dict(compact=True, unwrap_single=True)["food_id"] == "VN_COM_TAM"


class TwoPassDetector:
    def __init__(self) -> None:
        self.calls = 0

    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        self.calls += 1
        if self.calls == 1:
            return [Detection(26, "Com tam", 0.95, BoundingBox(5, 5, 95, 95))]
        return [
            Detection(25, "Com", 0.88, BoundingBox(5, 35, 45, 80)),
            Detection(54, "Thit nuong", 0.84, BoundingBox(50, 10, 82, 42)),
        ]


def test_second_pass_detects_components_inside_dish_crop() -> None:
    detector = TwoPassDetector()
    analyzer = FoodImageAnalyzer(
        detector,
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
        nutrition_catalog=NutritionCatalog(CATALOG),
        enable_component_pass=True,
    )

    result = analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8))

    assert detector.calls == 2
    assert len(result.items) == 3
    assert result.items[0].food["visual_components_matched"] == 2
    assert result.items[1].component_of == "VN_COM_TAM"
    assert result.items[2].component_of == "VN_COM_TAM"


class MultiInstanceComponentDetector:
    def __init__(self) -> None:
        self.calls = 0

    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        self.calls += 1
        if self.calls == 1:
            return [Detection(26, "Com tam", 0.96, BoundingBox(10, 10, 90, 90))]
        return [
            Detection(54, "Thit nuong", 0.91, BoundingBox(5, 8, 25, 28)),
            Detection(54, "Thit nuong", 0.88, BoundingBox(40, 8, 60, 28)),
            # Same physical piece as the first prediction; component NMS must remove it.
            Detection(54, "Thit nuong", 0.60, BoundingBox(6, 9, 25, 28)),
        ]


def test_component_pass_keeps_disjoint_pieces_and_aggregates_metric_weight() -> None:
    detector = MultiInstanceComponentDetector()
    analyzer = FoodImageAnalyzer(
        detector,
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
        nutrition_catalog=NutritionCatalog(CATALOG),
        enable_component_pass=True,
        component_crop_padding=0.10,
    )

    result = analyzer.analyze(
        np.zeros((100, 100, 3), dtype=np.uint8),
        cm_per_pixel=0.10,
    )

    food = result.items[0].food
    pork = next(
        component
        for component in food["estimated_components"]
        if component["ingredient_id"] == "grilled_pork"
    )
    pork_items = [item for item in result.items if item.label == "Thit nuong"]

    assert len(pork_items) == 2
    assert pork["basis"] == "visual_metric_estimate"
    assert pork["visual_instance_count"] == 2
    assert pork["estimated_g"] == round(sum(item.portion.weight_g for item in pork_items), 1)
    assert food["visual_components_matched"] == 1
    assert food["visual_instances_matched"] == 2
