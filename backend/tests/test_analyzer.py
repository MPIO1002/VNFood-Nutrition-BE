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

    result = analyzer.analyze(image, container_type="dia")
    payload = result.to_dict()
    json.dumps(payload)

    assert payload["image"] == {"width": 50, "height": 40}
    assert len(payload["items"]) == 1
    assert payload["items"][0]["label"] == "Com"
    assert payload["items"][0]["mask_polygons"]
    assert payload["items"][0]["portion"]["area_px"] == 400
    assert payload["items"][0]["portion"]["weight_g"] > 0


def test_human_class_is_filtered_by_default() -> None:
    class HumanDetector:
        def predict(self, image_rgb: np.ndarray) -> list[Detection]:
            return [Detection(27, "Con nguoi", 0.99, BoundingBox(1, 1, 10, 10))]

    analyzer = FoodImageAnalyzer(
        HumanDetector(),
        BoundingBoxSegmenter(),
        PortionEstimator(PRIORS),
    )
    image = np.zeros((40, 50, 3), dtype=np.uint8)

    result = analyzer.analyze(image)
    assert len(result.items) == 0
