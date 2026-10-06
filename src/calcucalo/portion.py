from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .domain import PortionEstimate, ScaleCalibration


@dataclass(frozen=True)
class FoodPrior:
    density_g_cm3: float
    thickness_cm: float
    default_mass_g: float
    relative_uncertainty: float
    geometry_uncertainty: float
    min_mass_g: float
    max_mass_g: float
    liquid: bool = False


class PortionEstimator:
    """Estimate mass from a mask and metric scale, with an honest no-scale fallback."""

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
            density_g_cm3=float(values.get("density_g_cm3", 0.9)),
            thickness_cm=float(values.get("thickness_cm", 2.0)),
            default_mass_g=float(values.get("default_mass_g", 180.0)),
            relative_uncertainty=float(values.get("relative_uncertainty", 0.5)),
            geometry_uncertainty=float(values.get("geometry_uncertainty", 0.3)),
            min_mass_g=float(values.get("min_mass_g", 10.0)),
            max_mass_g=float(values.get("max_mass_g", 1200.0)),
            liquid=self._key(label) in self.liquid_classes,
        )

    def estimate(
        self,
        label: str,
        mask: np.ndarray,
        calibration: ScaleCalibration | None,
        mask_confidence: float = 1.0,
        container_type: str | None = None,
        container_diameter_cm: float | None = None,
        container_length_cm: float | None = None,
        container_width_cm: float | None = None,
    ) -> PortionEstimate:
        prior = self.prior_for(label)
        area_px = int(np.count_nonzero(mask))

        # The visible surface of soup is not its volume. Without bowl geometry or RGB-D,
        # a class serving prior is safer than pretending surface area is liquid volume.
        # EXCEPT when we know the container is a bowl and have its diameter.
        # For box type: can calculate if we have length and width (no calibration needed)
        can_calculate_box = (
            prior.liquid
            and container_type == "hop"
            and container_length_cm is not None
            and container_width_cm is not None
        )
        # For round containers: need calibration + diameter
        can_calculate_bowl = (
            prior.liquid
            and container_type in ["to", "chen"]
            and container_diameter_cm is not None
            and calibration is not None
        )

        if (calibration is None or prior.liquid) and not can_calculate_bowl and not can_calculate_box:
            uncertainty = prior.relative_uncertainty + (1.0 - mask_confidence) * 0.15
            weight = float(np.clip(prior.default_mass_g, prior.min_mass_g, prior.max_mass_g))
            lower_g = max(0.0, weight * (1.0 - uncertainty))
            upper_g = weight * (1.0 + uncertainty)
            reason = "liquid_or_mixed_dish_prior" if prior.liquid else "single_image_serving_prior"
            assumptions = (
                "No metric volume is observable from one uncalibrated RGB image."
                if calibration is None
                else "Liquid depth is not observable from its top surface; using a serving prior."
            )
            return PortionEstimate(
                weight_g=weight,
                lower_g=lower_g,
                upper_g=upper_g,
                method=reason,
                confidence=max(0.15, 0.45 * mask_confidence),
                area_px=area_px,
                assumptions=(assumptions, "User correction or weighed calibration is recommended."),
                calculation={
                    "model": "serving_mass_prior",
                    "is_depth_measured": False,
                    "formula": "weight_g = clip(default_mass_g, min_mass_g, max_mass_g)",
                    "range_formula": (
                        "range_g = weight_g * (1 +/- effective_relative_uncertainty)"
                    ),
                    "inputs": {
                        "mask_area_px": area_px,
                        "mask_confidence": round(mask_confidence, 6),
                        "default_mass_g": round(prior.default_mass_g, 4),
                        "min_mass_g": round(prior.min_mass_g, 4),
                        "max_mass_g": round(prior.max_mass_g, 4),
                        "base_relative_uncertainty": round(prior.relative_uncertainty, 6),
                        "metric_scale_available": calibration is not None,
                        "liquid_or_mixed_dish": prior.liquid,
                    },
                    "intermediate": {
                        "mask_uncertainty_addition": round(
                            (1.0 - mask_confidence) * 0.15, 6
                        ),
                        "effective_relative_uncertainty": round(uncertainty, 6),
                    },
                    "outputs": {
                        "estimated_weight_g": round(weight, 4),
                        "lower_g": round(lower_g, 4),
                        "upper_g": round(upper_g, 4),
                    },
                },
            )

        # --- Box (Hộp): Calculate volume from actual physical dimensions ---
        if can_calculate_box:
            # Box depth is fixed at 4.5 cm (standard takeout box)
            depth_cm = 4.5
            # Use actual input dimensions directly — no camera pixel math needed
            volume_cm3 = container_length_cm * container_width_cm * depth_cm
            raw_weight = volume_cm3 * 1.0  # liquid density ≈ 1.0 g/cm3
            method = "box_lwh_x_liquid_density"
            assumptions_list = [
                f"Box dimensions: {container_length_cm:.1f} cm x {container_width_cm:.1f} cm.",
                f"Assumed box depth: {depth_cm:.2f} cm (takeout box standard).",
                "Assumed liquid density: 1.00 g/cm3.",
            ]
            area_cm2 = container_length_cm * container_width_cm
            weight = float(np.clip(raw_weight, prior.min_mass_g, prior.max_mass_g))
            uncertainty = 0.20 + (1.0 - mask_confidence) * 0.10
            confidence = max(0.15, min(0.75 * mask_confidence, 0.90))
            lower_g = max(0.0, weight * (1.0 - uncertainty))
            upper_g = weight * (1.0 + uncertainty)
            return PortionEstimate(
                weight_g=weight,
                lower_g=lower_g,
                upper_g=upper_g,
                method=method,
                confidence=confidence,
                area_px=area_px,
                area_cm2=area_cm2,
                volume_cm3=volume_cm3,
                assumptions=tuple(assumptions_list),
                calculation={
                    "model": "box_volume_from_dimensions",
                    "is_depth_measured": False,
                    "formula": "weight_g = length_cm * width_cm * depth_cm * liquid_density",
                    "inputs": {
                        "container_length_cm": container_length_cm,
                        "container_width_cm": container_width_cm,
                        "assumed_depth_cm": depth_cm,
                        "liquid_density_g_per_cm3": 1.0,
                    },
                    "outputs": {
                        "volume_cm3": round(volume_cm3, 4),
                        "estimated_weight_g": round(weight, 4),
                        "lower_g": round(lower_g, 4),
                        "upper_g": round(upper_g, 4),
                    },
                },
            )

        area_cm2 = area_px * calibration.cm_per_pixel**2
        # --- Round containers (Tô / Chén): Calculate depth from diameter ---
        if can_calculate_bowl:
            # Assume depth is 1/3 of the diameter for a bowl/cup
            depth_cm = container_diameter_cm / 3.0
            volume_cm3 = area_cm2 * depth_cm
            # Liquid soup typically has density close to 1.0
            raw_weight = volume_cm3 * 1.0
            method = "mask_area_x_bowl_depth_x_liquid_density"
            assumptions_list = [
                f"Assumed bowl depth: {depth_cm:.2f} cm (diameter/3).",
                "Assumed liquid density: 1.00 g/cm3.",
                "Perspective error should be minimized with a near top-down photo.",
            ]
        else:
            volume_cm3 = area_cm2 * prior.thickness_cm
            raw_weight = volume_cm3 * prior.density_g_cm3
            method = "mask_area_x_thickness_x_density"
            assumptions_list = [
                f"Assumed effective thickness: {prior.thickness_cm:.2f} cm.",
                f"Assumed density: {prior.density_g_cm3:.2f} g/cm3.",
                "Perspective error should be minimized with a near top-down photo.",
            ]
            
        weight = float(np.clip(raw_weight, prior.min_mass_g, prior.max_mass_g))
        uncertainty = prior.geometry_uncertainty + (1.0 - calibration.confidence) * 0.20
        uncertainty += (1.0 - mask_confidence) * 0.15
        confidence = 0.78 * calibration.confidence * mask_confidence
        lower_g = max(0.0, weight * (1.0 - uncertainty))
        upper_g = weight * (1.0 + uncertainty)
        return PortionEstimate(
            weight_g=weight,
            lower_g=lower_g,
            upper_g=upper_g,
            method=method,
            confidence=max(0.15, min(confidence, 0.90)),
            area_px=area_px,
            area_cm2=area_cm2,
            volume_cm3=volume_cm3,
            assumptions=tuple(assumptions_list),
            calculation={
                "model": "mask_area_x_assumed_thickness_x_density",
                "is_depth_measured": False,
                "formulas": [
                    "area_cm2 = mask_area_px * cm_per_pixel^2",
                    "volume_cm3 = area_cm2 * assumed_thickness_cm",
                    "raw_weight_g = volume_cm3 * assumed_density_g_cm3",
                    "estimated_weight_g = clip(raw_weight_g, min_mass_g, max_mass_g)",
                    "range_g = estimated_weight_g * (1 +/- effective_relative_uncertainty)",
                ],
                "inputs": {
                    "mask_area_px": area_px,
                    "mask_confidence": round(mask_confidence, 6),
                    "cm_per_pixel": round(calibration.cm_per_pixel, 8),
                    "calibration_method": calibration.method,
                    "calibration_confidence": round(calibration.confidence, 6),
                    "assumed_thickness_cm": round(prior.thickness_cm, 6),
                    "assumed_density_g_cm3": round(prior.density_g_cm3, 6),
                    "min_mass_g": round(prior.min_mass_g, 4),
                    "max_mass_g": round(prior.max_mass_g, 4),
                    "base_geometry_uncertainty": round(prior.geometry_uncertainty, 6),
                },
                "intermediate": {
                    "area_cm2": round(area_cm2, 6),
                    "volume_cm3": round(volume_cm3, 6),
                    "raw_weight_g": round(raw_weight, 6),
                    "weight_was_clamped": not np.isclose(raw_weight, weight),
                    "calibration_uncertainty_addition": round(
                        (1.0 - calibration.confidence) * 0.20, 6
                    ),
                    "mask_uncertainty_addition": round(
                        (1.0 - mask_confidence) * 0.15, 6
                    ),
                    "effective_relative_uncertainty": round(uncertainty, 6),
                },
                "outputs": {
                    "estimated_weight_g": round(weight, 4),
                    "lower_g": round(lower_g, 4),
                    "upper_g": round(upper_g, 4),
                    "confidence": round(max(0.15, min(confidence, 0.90)), 6),
                },
                "limitations": [
                    "Thickness is a class prior, not depth measured from the image.",
                    "Perspective correction is not applied; a near top-down image is required.",
                ],
            },
        )
