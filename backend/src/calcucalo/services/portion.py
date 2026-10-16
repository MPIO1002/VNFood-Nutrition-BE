from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..domain.models import PortionEstimate, ScaleCalibration


@dataclass(frozen=True)
class FoodPrior:
    default_mass_g: float
    relative_uncertainty: float
    min_mass_g: float
    max_mass_g: float
    expected_fill_ratio: float
    fill_ratio_uncertainty: float
    liquid: bool = False

CONTAINER_SCALE = {
    "chen": 0.4,        # Chén / bát nhỏ
    "to": 1.0,          # Tô vừa (chuẩn)
    "to_lon": 1.4,      # Tô lớn
    "dia_nho": 0.6,     # Đĩa nhỏ
    "dia": 1.0,         # Đĩa vừa (chuẩn)
    "dia_lon": 1.35,    # Đĩa lớn
    "hop": 0.85,        # Hộp xốp / khay cơm
}


class PortionEstimator:
    """Estimate mass from a mask and container fill-ratio, scaled with recipe priors."""

    def __init__(self, priors_path: str | Path) -> None:
        self.priors_path = Path(priors_path)
        with self.priors_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
        self.defaults: dict[str, Any] = config.get("defaults", {})
        self.foods: dict[str, dict[str, Any]] = config.get("foods", {})
        self.liquid_classes = {self._key(value) for value in config.get("liquid_classes", [])}
        self._food_lookup = {self._key(name): values for name, values in self.foods.items()}

    @staticmethod
    def _key(value: str) -> str:
        value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
        return " ".join(value.casefold().strip().split())

    def prior_for(self, label: str) -> FoodPrior:
        values = dict(self.defaults)
        values.update(self._food_lookup.get(self._key(label), {}))
        return FoodPrior(
            default_mass_g=float(values.get("default_mass_g", 180.0)),
            relative_uncertainty=float(values.get("relative_uncertainty", 0.5)),
            min_mass_g=float(values.get("min_mass_g", 10.0)),
            max_mass_g=float(values.get("max_mass_g", 1200.0)),
            expected_fill_ratio=float(values.get("expected_fill_ratio", 0.70)),
            fill_ratio_uncertainty=float(values.get("fill_ratio_uncertainty", 0.25)),
            liquid=self._key(label) in self.liquid_classes,
        )

    def estimate(
        self,
        label: str,
        mask: np.ndarray,
        calibration: ScaleCalibration | None = None,
        mask_confidence: float = 1.0,
        container_type: str | None = None,
        container_diameter_cm: float | None = None,
        container_length_cm: float | None = None,
        container_width_cm: float | None = None,
        plate_area_px: float | None = None,
        container_area_px: float | None = None,
        base_portion_g: float | None = None,
    ) -> PortionEstimate:
        prior = self.prior_for(label)
        area_px = int(np.count_nonzero(mask))

        # Support container_area_px or fallback to legacy plate_area_px
        effective_container_area = container_area_px if container_area_px is not None else plate_area_px

        # Base mass: prefer DB recipe base portion, fallback to class prior
        reference_mass = float(base_portion_g) if (base_portion_g is not None and base_portion_g > 0) else prior.default_mass_g
        container_scale = CONTAINER_SCALE.get(container_type, 1.0) if container_type else 1.0
        base_mass = reference_mass * container_scale

        if effective_container_area and effective_container_area > 0:
            fill_ratio = area_px / effective_container_area
            fill_ratio = max(0.05, min(fill_ratio, 1.5))
            portion_scale = fill_ratio / prior.expected_fill_ratio
            raw_weight = base_mass * portion_scale
            method = "fill_ratio_scaled_prior"
            uncertainty = prior.fill_ratio_uncertainty + (1.0 - mask_confidence) * 0.15
            assumptions_list = [
                f"Using fill ratio: {fill_ratio:.2f}.",
                f"Expected fill ratio: {prior.expected_fill_ratio:.2f}.",
                f"Container scale factor: {container_scale:.2f}.",
                f"Base recipe mass: {reference_mass:.1f}g.",
            ]
            calculation = {
                "model": "fill_ratio_scaled_prior",
                "is_depth_measured": False,
                "formula": "weight_g = base_recipe_mass * container_scale * (fill_ratio / expected_fill_ratio)",
                "inputs": {
                    "mask_area_px": area_px,
                    "container_area_px": round(effective_container_area, 2),
                    "base_recipe_mass_g": reference_mass,
                    "container_scale": container_scale,
                    "expected_fill_ratio": prior.expected_fill_ratio,
                },
                "intermediate": {
                    "fill_ratio": round(fill_ratio, 4),
                    "portion_scale": round(portion_scale, 4),
                },
                "outputs": {
                    "estimated_weight_g": round(raw_weight, 4),
                },
            }
        else:
            raw_weight = base_mass
            method = "serving_mass_prior"
            uncertainty = prior.relative_uncertainty + (1.0 - mask_confidence) * 0.15
            assumptions_list = [
                "No container boundary detected; using default serving prior.",
                f"Container scale factor: {container_scale:.2f}.",
                f"Base recipe mass: {reference_mass:.1f}g.",
            ]
            calculation = {
                "model": "serving_mass_prior",
                "is_depth_measured": False,
                "formula": "weight_g = base_recipe_mass * container_scale",
                "inputs": {
                    "base_recipe_mass_g": reference_mass,
                    "container_scale": container_scale,
                },
                "outputs": {
                    "estimated_weight_g": round(raw_weight, 4),
                },
            }

        weight = float(np.clip(raw_weight, prior.min_mass_g, prior.max_mass_g))
        confidence = max(0.15, 0.60 * mask_confidence)
        lower_g = max(0.0, weight * (1.0 - uncertainty))
        upper_g = weight * (1.0 + uncertainty)

        # Update calculation outputs with clamped values
        calculation["outputs"].update({
            "estimated_weight_g": round(weight, 4),
            "lower_g": round(lower_g, 4),
            "upper_g": round(upper_g, 4),
        })

        return PortionEstimate(
            weight_g=weight,
            lower_g=lower_g,
            upper_g=upper_g,
            method=method,
            confidence=confidence,
            area_px=area_px,
            assumptions=tuple(assumptions_list),
            calculation=calculation,
        )
