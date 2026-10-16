from pathlib import Path

import numpy as np
import pytest

from calcucalo.services.portion import PortionEstimator, CONTAINER_SCALE

PRIORS = Path(__file__).resolve().parents[1] / "configs" / "portion_priors.yaml"


def test_uncalibrated_image_without_container_uses_serving_prior() -> None:
    estimator = PortionEstimator(PRIORS)
    result = estimator.estimate("Com", np.ones((10, 10), dtype=bool), None)

    assert result.method == "serving_mass_prior"
    # "Com" has default_mass_g = 300 in portion_priors.yaml
    assert result.weight_g == 300.0
    trace = result.to_dict()["calculation"]
    assert trace["model"] == "serving_mass_prior"
    assert trace["inputs"]["base_recipe_mass_g"] == 300.0
    assert trace["inputs"]["container_scale"] == 1.0


def test_fill_ratio_scaled_prior_with_container_area() -> None:
    estimator = PortionEstimator(PRIORS)
    # For "Com", expected_fill_ratio = 0.65, default_mass_g = 300
    # Mask area = 650 px, container area = 1000 px -> fill_ratio = 0.65 -> portion_scale = 1.0 -> 300g
    mask = np.zeros((100, 100), dtype=bool)
    mask[:65, :10] = True  # 650 pixels
    assert np.count_nonzero(mask) == 650

    result = estimator.estimate(
        "Com",
        mask,
        container_type="dia",
        container_area_px=1000.0,
    )

    assert result.method == "fill_ratio_scaled_prior"
    assert result.weight_g == pytest.approx(300.0, rel=1e-2)
    trace = result.to_dict()["calculation"]
    assert trace["model"] == "fill_ratio_scaled_prior"
    assert trace["intermediate"]["fill_ratio"] == 0.65
    assert trace["intermediate"]["portion_scale"] == 1.0


def test_base_portion_g_from_db_recipe_is_used() -> None:
    estimator = PortionEstimator(PRIORS)
    # DB recipe specifies base portion is 400g
    mask = np.zeros((100, 100), dtype=bool)
    mask[:65, :10] = True  # 650 px / 1000 px = 0.65 fill ratio -> 1.0 scale

    result = estimator.estimate(
        "Com tam",
        mask,
        container_type="dia",
        container_area_px=1000.0,
        base_portion_g=400.0,
    )

    assert result.weight_g == pytest.approx(400.0, rel=1e-2)
    trace = result.to_dict()["calculation"]
    assert trace["inputs"]["base_recipe_mass_g"] == 400.0


def test_container_scale_factors_for_hop_and_chen() -> None:
    estimator = PortionEstimator(PRIORS)
    mask = np.ones((50, 50), dtype=bool)

    # Box (hop) container scale
    res_hop = estimator.estimate(
        "Com",
        mask,
        container_type="hop",
        container_area_px=5000.0,
        base_portion_g=200.0,
    )
    assert res_hop.to_dict()["calculation"]["inputs"]["container_scale"] == CONTAINER_SCALE["hop"]

    # Chen (small bowl) container scale
    res_chen = estimator.estimate(
        "Com",
        mask,
        container_type="chen",
        container_area_px=5000.0,
        base_portion_g=200.0,
    )
    assert res_chen.to_dict()["calculation"]["inputs"]["container_scale"] == CONTAINER_SCALE["chen"]


def test_model_label_with_english_suffix_matches_vietnamese_prior() -> None:
    estimator = PortionEstimator(PRIORS)
    result = estimator.estimate("Com (Rice)", np.ones((10, 10), dtype=bool), None)
    assert result.weight_g == 300.0
