from __future__ import annotations

import cv2
import numpy as np

from .domain import ScaleCalibration


class PlateScaleEstimator:
    """Estimate metric scale from a near-circular plate of known diameter."""


    def _detect_best_circle(self, image_rgb: np.ndarray) -> tuple[tuple[float, float, float], float] | None:
        height, width = image_rgb.shape[:2]
        shortest = min(height, width)
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (9, 9), 1.5)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(shortest // 3, 1),
            param1=100,
            param2=35,
            minRadius=max(int(shortest * 0.15), 5),
            maxRadius=max(int(shortest * 0.49), 6),
        )
        if circles is None:
            return None

        center_x, center_y = width / 2.0, height / 2.0
        candidates = circles[0]

        def score(circle: np.ndarray) -> float:
            x, y, radius = map(float, circle)
            center_distance = np.hypot(x - center_x, y - center_y) / max(shortest, 1)
            return radius / shortest - 0.5 * center_distance

        x, y, radius = map(float, max(candidates, key=score))
        diameter_px = 2.0 * radius
        if diameter_px <= 0:
            return None

        center_distance = np.hypot(x - center_x, y - center_y) / max(shortest, 1)
        confidence = float(np.clip(0.85 - center_distance, 0.35, 0.85))
        return (x, y, radius), confidence

    def detect_container_circle(self, image_rgb: np.ndarray) -> tuple[tuple[float, float, float], float] | None:
        return self._detect_best_circle(image_rgb)

    def estimate(self, image_rgb: np.ndarray, plate_diameter_cm: float) -> ScaleCalibration | None:
        if plate_diameter_cm <= 0:
            raise ValueError("plate_diameter_cm must be positive")
            
        result = self._detect_best_circle(image_rgb)
        if result is None:
            return None
            
        (x, y, radius), confidence = result
        diameter_px = 2.0 * radius
        return ScaleCalibration(
            cm_per_pixel=plate_diameter_cm / diameter_px,
            method="detected_plate",
            confidence=confidence,
            reference={
                "plate_diameter_cm": round(plate_diameter_cm, 2),
                "circle_xy_radius_px": [round(x, 1), round(y, 1), round(radius, 1)],
            },
            calculation={
                "model": "known_plate_diameter",
                "formula": "cm_per_pixel = plate_diameter_cm / plate_diameter_px",
                "inputs": {
                    "plate_diameter_cm": round(plate_diameter_cm, 4),
                    "plate_radius_px": round(radius, 4),
                    "plate_diameter_px": round(diameter_px, 4),
                },
                "outputs": {
                    "cm_per_pixel": round(plate_diameter_cm / diameter_px, 8),
                },
                "limitations": [
                    "The plate is assumed to be circular and photographed near top-down.",
                    "No perspective rectification is applied to an elliptical plate.",
                ],
            },
        )


def manual_scale(cm_per_pixel: float) -> ScaleCalibration:
    return ScaleCalibration(
        cm_per_pixel=cm_per_pixel,
        method="manual_scale",
        confidence=0.95,
        reference={"provided_by_client": True},
        calculation={
            "model": "client_provided_scale",
            "formula": "cm_per_pixel = client_provided_value",
            "inputs": {"client_provided_cm_per_pixel": round(cm_per_pixel, 8)},
            "outputs": {"cm_per_pixel": round(cm_per_pixel, 8)},
            "limitations": [
                "The caller is responsible for camera calibration and perspective correction."
            ],
        },
    )
