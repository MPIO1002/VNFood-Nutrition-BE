"""Domain models shared across the nutrition-analysis pipeline."""

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
]
