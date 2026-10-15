from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def assess_image_quality(image_rgb: np.ndarray) -> dict[str, Any]:
    """Return lightweight capture-quality signals for one RGB food image.

    These checks do not score whether the food prediction is correct. They only
    identify input conditions that commonly reduce detector and portion quality.
    """

    height, width = image_rgb.shape[:2]
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    brightness_mean = float(np.mean(gray))
    dark_pixel_ratio = float(np.mean(gray <= 25))
    bright_pixel_ratio = float(np.mean(gray >= 245))
    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    issues: list[str] = []
    recommendations: list[str] = []
    penalties = 0.0

    if min(width, height) < 480:
        issues.append("low_resolution")
        recommendations.append("Chụp ảnh có cạnh ngắn tối thiểu 480 px, nên từ 640 px trở lên.")
        penalties += 0.20

    if blur_variance < 45.0:
        issues.append("likely_blurry")
        recommendations.append("Giữ máy ổn định và lấy nét lại vào món ăn.")
        penalties += 0.30

    if brightness_mean < 45.0 or dark_pixel_ratio > 0.40:
        issues.append("too_dark")
        recommendations.append("Tăng ánh sáng đều, tránh để món ăn nằm trong vùng tối.")
        penalties += 0.25
    elif brightness_mean > 220.0 or bright_pixel_ratio > 0.35:
        issues.append("too_bright")
        recommendations.append("Giảm ánh sáng gắt và tránh vùng cháy sáng trên đĩa.")
        penalties += 0.25

    recommendations.append(
        "Chụp gần vuông góc với mặt đĩa và giữ trọn đĩa/bát trong khung hình."
    )
    score = max(0.0, min(1.0, 1.0 - penalties))
    status = "good" if not issues else "review"
    return {
        "status": status,
        "score": round(score, 3),
        "signals": {
            "width_px": width,
            "height_px": height,
            "brightness_mean": round(brightness_mean, 2),
            "dark_pixel_ratio": round(dark_pixel_ratio, 4),
            "bright_pixel_ratio": round(bright_pixel_ratio, 4),
            "blur_variance": round(blur_variance, 2),
        },
        "issues": issues,
        "recommendations": recommendations,
        "limitations": [
            "This heuristic cannot determine the true camera angle or recover hidden food depth."
        ],
    }
