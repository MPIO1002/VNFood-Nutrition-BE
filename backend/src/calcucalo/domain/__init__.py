"""Domain models shared across the nutrition-analysis pipeline."""

from .dish_nutrition import (
    PortionOutOfRangeError,
    compute_dish_nutrition,
    quantity_for_portion,
)
from .models import (
    AnalysisItem,
    AnalysisResult,
    BoundingBox,
    Detection,
    PortionEstimate,
)

__all__ = [
    "AnalysisItem",
    "AnalysisResult",
    "BoundingBox",
    "Detection",
    "PortionEstimate",
    "PortionOutOfRangeError",
    "compute_dish_nutrition",
    "quantity_for_portion",
]
