from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, median
from typing import Any, ClassVar


@dataclass
class NumericErrors:
    absolute: list[float] = field(default_factory=list)
    percentage: list[float] = field(default_factory=list)

    def add(self, expected: float, predicted: float) -> None:
        error = abs(predicted - expected)
        self.absolute.append(error)
        if expected != 0:
            self.percentage.append(error / abs(expected) * 100.0)

    def report(self) -> dict[str, float | int | None]:
        return {
            "count": len(self.absolute),
            "mae": round(mean(self.absolute), 3) if self.absolute else None,
            "median_ae": round(median(self.absolute), 3) if self.absolute else None,
            "mape_percent": round(mean(self.percentage), 3) if self.percentage else None,
        }


class EvaluationAccumulator:
    """Aggregate end-to-end dish, mass, calorie and macro errors."""

    FIELDS: ClassVar[dict[str, tuple[str, ...]]] = {
        "weight_g": ("estimated_portion_g",),
        "calories_kcal": ("estimated_totals", "calories_kcal"),
        "protein_g": ("estimated_totals", "protein_g"),
        "fat_g": ("estimated_totals", "fat_g"),
        "carb_g": ("estimated_totals", "carb_g"),
    }

    def __init__(self) -> None:
        self.samples = 0
        self.expected_foods = 0
        self.predicted_foods = 0
        self.matched_foods = 0
        self.errors = {field: NumericErrors() for field in self.FIELDS}
        self.per_food: dict[str, dict[str, NumericErrors]] = defaultdict(
            lambda: {field: NumericErrors() for field in self.FIELDS}
        )

    @staticmethod
    def _nested_value(payload: dict[str, Any], path: tuple[str, ...]) -> float | None:
        value: Any = payload
        for key in path:
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return float(value) if isinstance(value, (int, float)) else None

    def add_sample(
        self,
        expected: list[dict[str, Any]],
        predicted: list[dict[str, Any]],
    ) -> None:
        self.samples += 1
        self.expected_foods += len(expected)
        self.predicted_foods += len(predicted)
        candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for food in predicted:
            candidates[str(food.get("food_id"))].append(food)

        for truth in expected:
            food_id = str(truth["food_id"])
            matches = candidates.get(food_id, [])
            if not matches:
                continue
            prediction = matches.pop(0)
            self.matched_foods += 1
            for metric_name, path in self.FIELDS.items():
                if metric_name not in truth:
                    continue
                predicted_value = self._nested_value(prediction, path)
                if predicted_value is None:
                    continue
                expected_value = float(truth[metric_name])
                self.errors[metric_name].add(expected_value, predicted_value)
                self.per_food[food_id][metric_name].add(expected_value, predicted_value)

    def report(self) -> dict[str, Any]:
        precision = self.matched_foods / self.predicted_foods if self.predicted_foods else 0.0
        recall = self.matched_foods / self.expected_foods if self.expected_foods else 0.0
        return {
            "samples": self.samples,
            "food_detection": {
                "expected": self.expected_foods,
                "predicted": self.predicted_foods,
                "matched": self.matched_foods,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(2 * precision * recall / (precision + recall), 4)
                if precision + recall
                else 0.0,
            },
            "errors": {field: errors.report() for field, errors in self.errors.items()},
            "per_food": {
                food_id: {field: errors.report() for field, errors in metrics.items()}
                for food_id, metrics in sorted(self.per_food.items())
            },
        }
