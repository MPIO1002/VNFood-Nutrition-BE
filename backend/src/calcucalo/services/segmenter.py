from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from ..domain.models import Detection
from .masks import bbox_mask, normalize_mask


class Segmenter(Protocol):
    def segment(self, image_rgb: np.ndarray, detections: list[Detection]) -> list[np.ndarray]: ...


class BoundingBoxSegmenter:
    """Fast fallback. Useful for debugging, not for final portion measurements."""

    def segment(self, image_rgb: np.ndarray, detections: list[Detection]) -> list[np.ndarray]:
        shape = image_rgb.shape[:2]
        return [bbox_mask(shape, detection.bbox) for detection in detections]


class GrabCutSegmenter:
    """CPU fallback that refines each detector box into a foreground mask."""

    def __init__(self, iterations: int = 5) -> None:
        self.iterations = iterations

    def segment(self, image_rgb: np.ndarray, detections: list[Detection]) -> list[np.ndarray]:
        height, width = image_rgb.shape[:2]
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        output: list[np.ndarray] = []
        for detection in detections:
            box = detection.bbox.clipped(width, height)
            x1, y1 = int(box.x1), int(box.y1)
            x2, y2 = int(np.ceil(box.x2)), int(np.ceil(box.y2))
            if x2 - x1 < 3 or y2 - y1 < 3:
                output.append(bbox_mask((height, width), box))
                continue

            labels = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
            labels[y1:y2, x1:x2] = cv2.GC_PR_FGD

            inset_x = max(1, int((x2 - x1) * 0.18))
            inset_y = max(1, int((y2 - y1) * 0.18))
            if x1 + inset_x < x2 - inset_x and y1 + inset_y < y2 - inset_y:
                labels[y1 + inset_y : y2 - inset_y, x1 + inset_x : x2 - inset_x] = cv2.GC_FGD

            background_model = np.zeros((1, 65), np.float64)
            foreground_model = np.zeros((1, 65), np.float64)
            try:
                cv2.grabCut(
                    image_bgr,
                    labels,
                    None,
                    background_model,
                    foreground_model,
                    self.iterations,
                    cv2.GC_INIT_WITH_MASK,
                )
                mask = np.logical_or(labels == cv2.GC_FGD, labels == cv2.GC_PR_FGD)
                if np.count_nonzero(mask) < 9:
                    mask = bbox_mask((height, width), box)
            except cv2.error:
                mask = bbox_mask((height, width), box)
            output.append(mask)
        return output


class SamBoxSegmenter:
    """Prompt SAM/SAM2 with detector boxes for instance masks."""

    def __init__(self, model_path: str | Path = "sam2.1_t.pt", device: str | int | None = None) -> None:
        try:
            from ultralytics import SAM
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is required for SAM. Install with: pip install -e '.[inference]'"
            ) from exc
        self.model = SAM(str(model_path))
        self.device = device

    def segment(self, image_rgb: np.ndarray, detections: list[Detection]) -> list[np.ndarray]:
        if not detections:
            return []
        boxes = [detection.bbox.as_list(ndigits=4) for detection in detections]
        image_bgr = np.ascontiguousarray(image_rgb[:, :, ::-1])
        kwargs: dict[str, object] = {"bboxes": boxes, "verbose": False}
        if self.device is not None:
            kwargs["device"] = self.device
        results = self.model.predict(image_bgr, **kwargs)
        if not results or results[0].masks is None:
            return BoundingBoxSegmenter().segment(image_rgb, detections)

        raw_masks = results[0].masks.data.cpu().numpy()
        masks = [normalize_mask(mask, image_rgb.shape[:2]) for mask in raw_masks]
        if len(masks) != len(detections):
            return BoundingBoxSegmenter().segment(image_rgb, detections)
        return masks


def create_segmenter(name: str, sam_model: str = "sam2.1_t.pt", device: str | int | None = None) -> Segmenter:
    normalized = name.strip().lower()
    if normalized == "sam":
        return SamBoxSegmenter(sam_model, device=device)
    if normalized == "grabcut":
        return GrabCutSegmenter()
    if normalized in {"bbox", "box", "none"}:
        return BoundingBoxSegmenter()
    raise ValueError(f"Unknown segmenter '{name}'. Use: sam, grabcut or bbox")

