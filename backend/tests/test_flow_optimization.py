from pathlib import Path

import numpy as np
import pytest

from calcucalo.domain.models import BoundingBox, Detection
from calcucalo.services.analyzer import FoodImageAnalyzer
from calcucalo.services.portion import CONTAINER_SCALE, PortionEstimator
from calcucalo.services.segmenter import BoundingBoxSegmenter

PRIORS = Path(__file__).resolve().parents[1] / "configs" / "portion_priors.yaml"


class MockNutritionDB:
    def base_portion_for(self, label: str) -> float | None:
        if "com tam" in label.lower():
            return 450.0  # 450g standard serving
        return None

    def analyze(self, label: str, estimated_portion_g: float | None = None, portion_method: str | None = None):
        base_g = 450.0
        portion_g = estimated_portion_g or base_g
        scale = portion_g / base_g
        return {
            "food_id": "DB_COM_TAM",
            "name": "Cơm tấm",
            "base_portion_g": base_g,
            "estimated_portion_g": round(portion_g, 1),
            "estimated_components": [
                {
                    "ingredient_id": "1",
                    "name": "Cơm tấm",
                    "estimated_g": round(200.0 * scale, 1),
                    "calories_kcal": round(260.0 * scale, 1),
                },
                {
                    "ingredient_id": "2",
                    "name": "Sườn nướng",
                    "estimated_g": round(150.0 * scale, 1),
                    "calories_kcal": round(350.0 * scale, 1),
                },
            ],
            "estimated_totals": {
                "calories_kcal": round(610.0 * scale, 1),
                "protein_g": round(35.0 * scale, 1),
                "fat_g": round(22.0 * scale, 1),
                "carb_g": round(65.0 * scale, 1),
            },
        }


class MockDetector:
    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        return [Detection(26, "Com tam", 0.95, BoundingBox(50, 50, 150, 150))]


def test_full_pipeline_with_round_plate():
    estimator = PortionEstimator(PRIORS)
    catalog = MockNutritionDB()
    analyzer = FoodImageAnalyzer(
        MockDetector(),
        BoundingBoxSegmenter(),
        estimator,
        nutrition_catalog=catalog,
    )

    image = np.zeros((300, 300, 3), dtype=np.uint8)

    # Test round plate without specifying dimensions (user just chooses "dia")
    result = analyzer.analyze(image, container_type="dia")

    assert len(result.items) == 1
    item = result.items[0]
    assert item.label == "Com tam"
    assert item.food is not None
    assert item.food["name"] == "Cơm tấm"
    assert "estimated_totals" in item.food
    assert item.food["estimated_totals"]["calories_kcal"] > 0
    assert len(item.food["estimated_components"]) == 2


def test_full_pipeline_with_rectangular_box():
    estimator = PortionEstimator(PRIORS)
    catalog = MockNutritionDB()
    analyzer = FoodImageAnalyzer(
        MockDetector(),
        BoundingBoxSegmenter(),
        estimator,
        nutrition_catalog=catalog,
    )

    image = np.zeros((300, 300, 3), dtype=np.uint8)

    # Test box ("hop") without requiring width/length dimensions!
    result = analyzer.analyze(image, container_type="hop")

    assert len(result.items) == 1
    item = result.items[0]
    assert item.portion.weight_g > 0
    # Container scale factor for hop was applied
    assert item.portion.calculation["inputs"]["container_scale"] == CONTAINER_SCALE["hop"]
    assert item.food is not None
    assert item.food["estimated_portion_g"] == pytest.approx(item.portion.weight_g, rel=1e-1)


def test_fill_ratio_adjusts_portion_and_nutrition():
    estimator = PortionEstimator(PRIORS)
    # Expected fill ratio for com tam is 0.65
    # 6500 px mask on 10,000 px container -> fill_ratio = 0.65 -> portion scale = 1.0
    mask = np.zeros((200, 200), dtype=bool)
    mask[:65, :100] = True  # 6500 px
    
    portion = estimator.estimate(
        "Com tam",
        mask,
        container_type="dia",
        container_area_px=10000.0,
        base_portion_g=450.0,
    )
    assert portion.weight_g == pytest.approx(450.0, rel=1e-2)
    assert portion.method == "fill_ratio_scaled_prior"

    # Now half portion: 3250 px -> fill_ratio = 0.325 -> portion should be ~225g
    mask_half = np.zeros((200, 200), dtype=bool)
    mask_half[:65, :50] = True  # 3250 px
    portion_half = estimator.estimate(
        "Com tam",
        mask_half,
        container_type="dia",
        container_area_px=10000.0,
        base_portion_g=450.0,
    )
    assert portion_half.weight_g == pytest.approx(225.0, rel=1e-1)
