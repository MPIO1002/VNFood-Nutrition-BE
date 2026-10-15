import json
from pathlib import Path

import numpy as np

from calcucalo.domain.models import BoundingBox, Detection
from calcucalo.services.analyzer import FoodImageAnalyzer
from calcucalo.services.portion import PortionEstimator
from calcucalo.services.segmenter import BoundingBoxSegmenter

PRIORS = Path(__file__).resolve().parents[1] / "configs" / "portion_priors.yaml"


class FakeDetector:
    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        return [Detection(25, "Com", 0.91, BoundingBox(10, 10, 30, 30))]


def test_end_to_end_analysis_serializes_detection_mask_and_portion() -> None:
    analyzer = FoodImageAnalyzer(
        FakeDetector(),
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
    )
    image = np.zeros((40, 50, 3), dtype=np.uint8)

    result = analyzer.analyze(image, cm_per_pixel=0.2)
    payload = result.to_dict()
    json.dumps(payload)

    assert payload["image"] == {"width": 50, "height": 40}
    assert payload["calculation_trace"] == {
        "schema_version": "1.0",
        "measurement_status": "estimated_not_measured",
        "metric_scale_available": True,
        "depth_measurement_available": False,
        "notes": [
            "A reported volume may use class-level assumed thickness.",
            "Inspect each portion.calculation.model and is_depth_measured field.",
        ],
    }
    assert payload["calibration"]["method"] == "manual_scale"
    assert payload["calibration"]["calculation"]["inputs"] == {
        "client_provided_cm_per_pixel": 0.2
    }
    assert len(payload["items"]) == 1
    assert payload["items"][0]["label"] == "Com"
    assert payload["items"][0]["mask_polygons"]
    assert payload["items"][0]["portion"]["area_px"] == 400
    calculation = payload["items"][0]["portion"]["calculation"]
    assert calculation["model"] == "mask_area_x_assumed_thickness_x_density"
    assert calculation["intermediate"]["area_cm2"] == 16.0
    assert calculation["intermediate"]["volume_cm3"] == 44.8


def test_human_class_is_filtered_by_default() -> None:
    class HumanDetector:
        def predict(self, image_rgb: np.ndarray) -> list[Detection]:
            return [Detection(27, "Con nguoi", 0.99, BoundingBox(1, 1, 10, 10))]

    analyzer = FoodImageAnalyzer(
        HumanDetector(),
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
    )
    result = analyzer.analyze(np.zeros((20, 20, 3), dtype=np.uint8))

    assert not result.items
