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
