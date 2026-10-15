from __future__ import annotations

import cv2
import numpy as np

from ..domain.models import BoundingBox


def normalize_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Convert a model mask to a boolean mask at the requested (height, width)."""
    if mask.ndim > 2:
        mask = np.squeeze(mask)
    if mask.ndim != 2:
        raise ValueError(f"Mask must be 2D after squeeze, got {mask.shape}")
    if mask.shape != shape:
        mask = cv2.resize(mask.astype(np.float32), (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return np.asarray(mask > 0.5, dtype=bool)


def bbox_mask(shape: tuple[int, int], bbox: BoundingBox) -> np.ndarray:
    height, width = shape
    box = bbox.clipped(width, height)
    x1, y1 = int(box.x1), int(box.y1)
    x2, y2 = int(np.ceil(box.x2)), int(np.ceil(box.y2))
    mask = np.zeros(shape, dtype=bool)
    mask[y1:y2, x1:x2] = True
    return mask


def mask_to_polygons(
    mask: np.ndarray,
    min_area_px: float = 25.0,
    epsilon_ratio: float = 0.005,
) -> list[list[list[int]]]:
    """Return external contours as compact JSON-friendly polygons."""
    binary = np.asarray(mask, dtype=np.uint8) * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polygons: list[list[list[int]]] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(contour) < min_area_px:
            continue
        epsilon = epsilon_ratio * cv2.arcLength(contour, closed=True)
        simplified = cv2.approxPolyDP(contour, epsilon, closed=True).reshape(-1, 2)
        if len(simplified) >= 3:
            polygons.append([[int(x), int(y)] for x, y in simplified])
    return polygons


def mask_quality(mask: np.ndarray, bbox: BoundingBox) -> float:
    """Simple mask sanity score; it is not a calibrated probability."""
    mask_area = int(np.count_nonzero(mask))
    box_area = max(bbox.width * bbox.height, 1.0)
    ratio = mask_area / box_area
    if ratio < 0.03 or ratio > 1.05:
        return 0.2
    if 0.15 <= ratio <= 0.95:
        return 1.0
    return 0.65

