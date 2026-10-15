from pathlib import Path

import numpy as np
import pytest

from calcucalo.domain.models import ScaleCalibration
from calcucalo.services.portion import PortionEstimator

PRIORS = Path(__file__).resolve().parents[1] / "configs" / "portion_priors.yaml"


def test_calibrated_solid_uses_mask_area_density_and_thickness() -> None:
    estimator = PortionEstimator(PRIORS)
    mask = np.ones((100, 100), dtype=bool)
    calibration = ScaleCalibration(0.1, "test", 1.0)

    result = estimator.estimate("Com", mask, calibration)

    assert result.method == "mask_area_x_thickness_x_density"
    assert result.area_cm2 == pytest.approx(100.0)
    assert result.volume_cm3 == pytest.approx(280.0)
    assert result.weight_g == pytest.approx(201.6)
    trace = result.to_dict()["calculation"]
    assert trace["is_depth_measured"] is False
    assert trace["inputs"]["assumed_thickness_cm"] == pytest.approx(2.8)
    assert trace["inputs"]["assumed_density_g_cm3"] == pytest.approx(0.72)
    assert trace["intermediate"]["raw_weight_g"] == pytest.approx(201.6)
    assert trace["outputs"]["estimated_weight_g"] == pytest.approx(201.6)


def test_uncalibrated_image_returns_explicit_serving_prior() -> None:
    estimator = PortionEstimator(PRIORS)
    result = estimator.estimate("Com", np.ones((10, 10), dtype=bool), None)

    assert result.method == "single_image_serving_prior"
    assert result.weight_g == 180.0
    assert result.lower_g == 90.0
    assert result.upper_g == 270.0
    trace = result.to_dict()["calculation"]
    assert trace["model"] == "serving_mass_prior"
    assert trace["inputs"]["metric_scale_available"] is False
    assert trace["intermediate"]["effective_relative_uncertainty"] == 0.5


def test_liquid_never_converts_visible_surface_directly_to_volume() -> None:
    estimator = PortionEstimator(PRIORS)
    calibration = ScaleCalibration(0.1, "test", 1.0)
    result = estimator.estimate("Pho", np.ones((100, 100), dtype=bool), calibration)

    assert result.method == "liquid_or_mixed_dish_prior"
    assert result.weight_g == 550.0
    assert result.volume_cm3 is None
    trace = result.to_dict()["calculation"]
    assert trace["inputs"]["metric_scale_available"] is True
    assert trace["inputs"]["liquid_or_mixed_dish"] is True
    assert trace["is_depth_measured"] is False


def test_model_label_with_english_suffix_matches_vietnamese_prior() -> None:
    estimator = PortionEstimator(PRIORS)

    result = estimator.estimate("Com (Rice)", np.ones((10, 10), dtype=bool), None)

    assert result.weight_g == 180.0
