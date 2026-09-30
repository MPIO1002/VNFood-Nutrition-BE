"""CalcuCalo image-analysis baseline."""

from .analyzer import FoodImageAnalyzer
from .detector import OnnxYoloDetector, UltralyticsDetector
from .nutrition import NutritionCatalog
from .portion import PortionEstimator

__all__ = [
    "FoodImageAnalyzer",
    "NutritionCatalog",
    "OnnxYoloDetector",
    "PortionEstimator",
    "UltralyticsDetector",
]
__version__ = "0.5.1"
