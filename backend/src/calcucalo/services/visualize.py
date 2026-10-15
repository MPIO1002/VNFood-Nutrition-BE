from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..domain.models import AnalysisResult

_COLORS = [
    (46, 204, 113),
    (52, 152, 219),
    (241, 196, 15),
    (231, 76, 60),
    (155, 89, 182),
]


def render_overlay(image_rgb: np.ndarray, result: AnalysisResult) -> np.ndarray:
    canvas = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    overlay = canvas.copy()
    for index, item in enumerate(result.items):
        color = _COLORS[index % len(_COLORS)]
        for polygon in item.polygons:
            points = np.asarray(polygon, dtype=np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(overlay, [points], color)
    canvas = cv2.addWeighted(overlay, 0.28, canvas, 0.72, 0)

    for index, item in enumerate(result.items):
        color = _COLORS[index % len(_COLORS)]
        x1, y1, x2, y2 = map(int, item.bbox.as_list(ndigits=0))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        text = f"{item.label} {item.detection_confidence:.0%} | {item.portion.weight_g:.0f} g"
        cv2.putText(
            canvas,
            text,
            (x1, max(18, y1 - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
            cv2.LINE_AA,
        )
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)


def save_overlay(path: str | Path, image_rgb: np.ndarray, result: AnalysisResult) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = cv2.cvtColor(render_overlay(image_rgb, result), cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(target), rendered):
        raise OSError(f"Could not write overlay to {target}")

