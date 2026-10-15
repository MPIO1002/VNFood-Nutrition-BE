from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError(f"Invalid xyxy bounding box: {self}")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    def clipped(self, image_width: int, image_height: int) -> BoundingBox:
        x1 = min(max(self.x1, 0.0), max(image_width - 1, 0))
        y1 = min(max(self.y1, 0.0), max(image_height - 1, 0))
        x2 = min(max(self.x2, x1 + 1.0), float(image_width))
        y2 = min(max(self.y2, y1 + 1.0), float(image_height))
        return BoundingBox(x1, y1, x2, y2)

    def as_list(self, ndigits: int = 2) -> list[float]:
        return [round(v, ndigits) for v in (self.x1, self.y1, self.x2, self.y2)]


@dataclass
class Detection:
    class_id: int
    label: str
    confidence: float
    bbox: BoundingBox
    mask: np.ndarray | None = None


@dataclass(frozen=True)
class ScaleCalibration:
    cm_per_pixel: float
    method: str
    confidence: float
    reference: dict[str, Any] = field(default_factory=dict)
    calculation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cm_per_pixel <= 0:
            raise ValueError("cm_per_pixel must be positive")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "cm_per_pixel": round(self.cm_per_pixel, 6),
            "method": self.method,
            "confidence": round(self.confidence, 3),
            "reference": self.reference,
        }
        if self.calculation:
            result["calculation"] = self.calculation
        return result


@dataclass(frozen=True)
class PortionEstimate:
    weight_g: float
    lower_g: float
    upper_g: float
    method: str
    confidence: float
    area_px: int
    area_cm2: float | None = None
    volume_cm3: float | None = None
    assumptions: tuple[str, ...] = ()
    calculation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "weight_g": round(self.weight_g, 1),
            "range_g": [round(self.lower_g, 1), round(self.upper_g, 1)],
            "method": self.method,
            "confidence": round(self.confidence, 3),
            "area_px": self.area_px,
            "assumptions": list(self.assumptions),
        }
        if self.area_cm2 is not None:
            result["area_cm2"] = round(self.area_cm2, 2)
        if self.volume_cm3 is not None:
            result["volume_cm3"] = round(self.volume_cm3, 2)
        if self.calculation:
            result["calculation"] = self.calculation
        return result


@dataclass
class AnalysisItem:
    class_id: int
    label: str
    detection_confidence: float
    bbox: BoundingBox
    polygons: list[list[list[int]]]
    portion: PortionEstimate
    food: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "class_id": self.class_id,
            "label": self.label,
            "detection_confidence": round(self.detection_confidence, 4),
            "bbox_xyxy": self.bbox.as_list(),
            "mask_polygons": self.polygons,
            "portion": self.portion.to_dict(),
        }
        if self.food is not None:
            result["food"] = self.food
        return result


@dataclass
class AnalysisResult:
    image_width: int
    image_height: int
    items: list[AnalysisItem]
    calibration: ScaleCalibration | None
    warnings: list[str] = field(default_factory=list)
    image_quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": {"width": self.image_width, "height": self.image_height},
            "image_quality": self.image_quality,
            "calibration": self.calibration.to_dict() if self.calibration else None,
            "calculation_trace": {
                "schema_version": "1.0",
                "measurement_status": "estimated_not_measured",
                "metric_scale_available": self.calibration is not None,
                "depth_measurement_available": False,
                "notes": [
                    "A reported volume may use class-level assumed thickness.",
                    "Inspect each portion.calculation.model and is_depth_measured field.",
                ],
            },
            "items": [item.to_dict() for item in self.items],
            "foods": [item.food for item in self.items if item.food is not None],
            "warnings": self.warnings,
        }

    def to_nutrition_dict(
        self,
        *,
        compact: bool = True,
        unwrap_single: bool = True,
    ) -> dict[str, Any]:
        from .nutrition import NutritionCatalog

        foods = [item.food for item in self.items if item.food is not None]
        if compact:
            foods = [NutritionCatalog.compact(food) for food in foods]
        if unwrap_single and len(foods) == 1:
            return foods[0]
        return {"foods": foods, "warnings": self.warnings}
