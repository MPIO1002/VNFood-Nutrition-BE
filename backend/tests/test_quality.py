import numpy as np

from calcucalo.services.quality import assess_image_quality


def test_quality_flags_dark_blurry_low_resolution_image() -> None:
    report = assess_image_quality(np.zeros((200, 300, 3), dtype=np.uint8))

    assert report["status"] == "review"
    assert report["score"] < 0.5
    assert set(report["issues"]) == {"low_resolution", "likely_blurry", "too_dark"}
    assert report["signals"]["width_px"] == 300
    assert report["signals"]["height_px"] == 200


def test_quality_accepts_well_exposed_sharp_image() -> None:
    checker = (80 + np.indices((640, 640)).sum(axis=0) % 2 * 100).astype(np.uint8)
    image = np.repeat(checker[:, :, None], 3, axis=2)

    report = assess_image_quality(image)

    assert report["status"] == "good"
    assert report["score"] == 1.0
    assert report["issues"] == []
