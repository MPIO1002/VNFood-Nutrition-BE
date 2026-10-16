import cv2
import numpy as np
import pytest

from calcucalo.services.calibration import PlateScaleEstimator


def test_plate_calibration_exposes_scale_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    circles = np.asarray([[[50.0, 50.0, 40.0]]], dtype=np.float32)
    monkeypatch.setattr(cv2, "HoughCircles", lambda *args, **kwargs: circles)

    calibration = PlateScaleEstimator().estimate(
        np.zeros((100, 100, 3), dtype=np.uint8),
        plate_diameter_cm=20.0,
    )

    assert calibration is not None
    assert calibration.cm_per_pixel == pytest.approx(0.25)
    trace = calibration.to_dict()["calculation"]
    assert trace["formula"] == "cm_per_pixel = plate_diameter_cm / plate_diameter_px"
    assert trace["inputs"]["plate_diameter_px"] == 80.0
    assert trace["outputs"]["cm_per_pixel"] == 0.25


def test_detect_container_circle(monkeypatch: pytest.MonkeyPatch) -> None:
    circles = np.asarray([[[50.0, 50.0, 30.0]]], dtype=np.float32)
    monkeypatch.setattr(cv2, "HoughCircles", lambda *args, **kwargs: circles)

    estimator = PlateScaleEstimator()
    res = estimator.detect_container_area(np.zeros((100, 100, 3), dtype=np.uint8), container_type="dia")
    assert res is not None
    area, shape, conf = res
    assert shape == "circle"
    assert area == pytest.approx(3.14159265 * 900.0)


def test_detect_container_box() -> None:
    # Create an image with a clear rectangular white box on black background
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (250, 250), (255, 255, 255), -1)

    estimator = PlateScaleEstimator()
    res = estimator.detect_container_area(img, container_type="hop")
    assert res is not None
    area, shape, conf = res
    assert shape == "rectangle"
    assert area == pytest.approx(40000.0, rel=0.15)
