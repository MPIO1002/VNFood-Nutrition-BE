"""CalcuCalo image-analysis baseline."""

from .repositories.nutrition import NutritionCatalog
from .services.analyzer import FoodImageAnalyzer
from .services.detector import OnnxYoloDetector, UltralyticsDetector
from .services.portion import PortionEstimator

__all__ = [
    "FoodImageAnalyzer",
    "NutritionCatalog",
    "OnnxYoloDetector",
    "PortionEstimator",
    "UltralyticsDetector",
]
__version__ = "0.5.1"
