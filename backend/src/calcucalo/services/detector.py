from __future__ import annotations

import ast
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
import yaml

from ..domain.models import BoundingBox, Detection
from .masks import normalize_mask


class Detector(Protocol):
    def predict(self, image_rgb: np.ndarray) -> list[Detection]: ...

    def info(self) -> dict[str, object]: ...


class UltralyticsDetector:
    """Adapter for PyTorch or ONNX YOLO detect/segment models."""

    def __init__(
        self,
        model_path: str | Path,
        confidence: float = 0.25,
        iou: float = 0.60,
        image_size: int = 640,
        device: str | int | None = None,
    ) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is required for inference. Install with: pip install -e '.[inference]'"
            ) from exc

        self.model_path = str(model_path)
        self.model = YOLO(self.model_path)
        self.confidence = confidence
        self.iou = iou
        self.image_size = image_size
        self.device = device

    def info(self) -> dict[str, object]:
        names = getattr(self.model, "names", {}) or {}
        checkpoint = getattr(self.model, "ckpt", None) or {}
        train_args = checkpoint.get("train_args") or {}
        train_metrics = checkpoint.get("train_metrics") or {}
        metric_keys = (
            "metrics/precision(B)",
            "metrics/recall(B)",
            "metrics/mAP50(B)",
            "metrics/mAP50-95(B)",
        )
        metrics = {
            key: round(float(train_metrics[key]), 6)
            for key in metric_keys
            if train_metrics.get(key) is not None
        }
        training = {
            key: train_args[key]
            for key in ("model", "epochs", "fraction", "imgsz", "batch")
            if train_args.get(key) is not None
        }
        planned_epochs = train_args.get("epochs")
        checkpoint_epoch = checkpoint.get("epoch")
        if isinstance(checkpoint_epoch, (int, float)) and checkpoint_epoch >= 0:
            completed_epochs = int(checkpoint_epoch) + 1
            training["completed_epochs"] = completed_epochs
            if isinstance(planned_epochs, (int, float)) and planned_epochs > 0:
                training["planned_epochs"] = int(planned_epochs)
                training["training_complete"] = completed_epochs >= int(planned_epochs)
        elif (
            checkpoint_epoch == -1
            and checkpoint.get("optimizer") is None
            and isinstance(planned_epochs, (int, float))
            and planned_epochs > 0
        ):
            # Ultralytics strips the optimizer and writes epoch=-1 after a completed run.
            training["completed_epochs"] = int(planned_epochs)
            training["planned_epochs"] = int(planned_epochs)
            training["training_complete"] = True
        return {
            "backend": "ultralytics",
            "format": Path(self.model_path).suffix.casefold().lstrip("."),
            "model_file": Path(self.model_path).name,
            "task": str(getattr(self.model, "task", "detect")),
            "class_count": len(names),
            "classes": {str(key): str(value) for key, value in dict(names).items()},
            "confidence_threshold": self.confidence,
            "iou_threshold": self.iou,
            "image_size": self.image_size,
            "device": "auto" if self.device is None else str(self.device),
            "training": training,
            "metrics": metrics,
        }

    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        # Ultralytics interprets NumPy arrays as OpenCV/BGR images.
        image_bgr = np.ascontiguousarray(image_rgb[:, :, ::-1])
        kwargs = {
            "source": image_bgr,
            "conf": self.confidence,
            "iou": self.iou,
            "imgsz": self.image_size,
            "verbose": False,
        }
        if self.device is not None:
            kwargs["device"] = self.device
        results = self.model.predict(**kwargs)
        if not results:
            return []

        result = results[0]
        height, width = image_rgb.shape[:2]
        names = result.names
        masks: list[np.ndarray] = []
        if result.masks is not None:
            masks = [normalize_mask(item, (height, width)) for item in result.masks.data.cpu().numpy()]

        detections: list[Detection] = []
        if result.boxes is None:
            return detections
        for index, box in enumerate(result.boxes):
            xyxy = box.xyxy[0].detach().cpu().numpy().tolist()
            class_id = int(box.cls[0].item())
            label = str(names[class_id])
            detections.append(
                Detection(
                    class_id=class_id,
                    label=label,
                    confidence=float(box.conf[0].item()),
                    bbox=BoundingBox(*map(float, xyxy)).clipped(width, height),
                    mask=masks[index] if index < len(masks) else None,
                )
            )
        return detections


class OnnxYoloDetector:
    """Lightweight ONNX Runtime backend for YOLO detect models.

    It supports end-to-end YOLOv10 output ``N x 6`` and raw Ultralytics
    detection output ``N x (4 + classes)``. Segmentation ONNX models should
    use :class:`UltralyticsDetector` so prototype masks are decoded correctly.
    """

    def __init__(
        self,
        model_path: str | Path,
        classes_path: str | Path | None = None,
        confidence: float = 0.25,
        iou: float = 0.60,
        image_size: int | None = None,
        device: str | int | None = None,
    ) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                "ONNX Runtime is required. Install with: pip install -e '.[onnx]'"
            ) from exc

        available = ort.get_available_providers()
        device_text = str(device).casefold()
        requested_gpu = (
            isinstance(device, int) or device_text.isdecimal() or device_text in {"cuda", "gpu"}
        )
        if requested_gpu and "CUDAExecutionProvider" not in available:
            raise RuntimeError(
                "CUDA was requested but this ONNX Runtime build has no CUDA provider. "
                "Install onnxruntime-gpu or use --device cpu."
            )
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if requested_gpu
            else ["CPUExecutionProvider"]
        )
        self.model_path = str(model_path)
        self.session = ort.InferenceSession(self.model_path, providers=providers)
        model_input = self.session.get_inputs()[0]
        self.input_name = model_input.name
        self.input_dtype = np.float16 if "float16" in model_input.type else np.float32
        self.output_names = [item.name for item in self.session.get_outputs()]
        shape = model_input.shape
        model_height = shape[2] if len(shape) == 4 and isinstance(shape[2], int) else image_size
        model_width = shape[3] if len(shape) == 4 and isinstance(shape[3], int) else image_size
        self.input_height = int(model_height or 640)
        self.input_width = int(model_width or 640)
        self.confidence = confidence
        self.iou = iou
        self.names = self._load_names(classes_path)

    def info(self) -> dict[str, object]:
        metadata = self.session.get_modelmeta().custom_metadata_map
        training: dict[str, object] = {}
        embedded_args = metadata.get("args")
        if embedded_args:
            try:
                parsed = ast.literal_eval(embedded_args)
                if isinstance(parsed, dict):
                    training = {
                        key: parsed[key]
                        for key in ("model", "epochs", "fraction", "imgsz", "batch")
                        if parsed.get(key) is not None
                    }
            except (SyntaxError, ValueError):
                pass
        return {
            "backend": "onnxruntime",
            "format": "onnx",
            "model_file": Path(self.model_path).name,
            "task": metadata.get("task", "detect"),
            "class_count": len(self.names),
            "classes": {str(key): value for key, value in self.names.items()},
            "confidence_threshold": self.confidence,
            "iou_threshold": self.iou,
            "image_size": [self.input_height, self.input_width],
            "device": self.session.get_providers()[0],
            "training": training,
            "metrics": {},
        }

    def _load_names(self, classes_path: str | Path | None) -> dict[int, str]:
        metadata = self.session.get_modelmeta().custom_metadata_map
        embedded = metadata.get("names")
        if embedded:
            try:
                parsed = ast.literal_eval(embedded)
                if isinstance(parsed, dict):
                    return {int(key): str(value) for key, value in parsed.items()}
                if isinstance(parsed, list):
                    return dict(enumerate(map(str, parsed)))
            except (SyntaxError, ValueError):
                pass
        if classes_path is None:
            raise ValueError("ONNX model has no class metadata; provide classes_path")
        with Path(classes_path).open("r", encoding="utf-8") as stream:
            values = (yaml.safe_load(stream) or {}).get("names", {})
        if isinstance(values, list):
            return dict(enumerate(map(str, values)))
        return {int(key): str(value) for key, value in values.items()}

    def _preprocess(self, image_rgb: np.ndarray) -> tuple[np.ndarray, float, float, float]:
        height, width = image_rgb.shape[:2]
        ratio = min(self.input_width / width, self.input_height / height)
        resized_width = max(1, round(width * ratio))
        resized_height = max(1, round(height * ratio))
        resized = cv2.resize(image_rgb, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        pad_x = (self.input_width - resized_width) / 2.0
        pad_y = (self.input_height - resized_height) / 2.0
        left, top = round(pad_x - 0.1), round(pad_y - 0.1)
        right = self.input_width - resized_width - left
        bottom = self.input_height - resized_height - top
        padded = cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )
        tensor = padded.astype(self.input_dtype) / self.input_dtype(255.0)
        tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None])
        return tensor, ratio, float(left), float(top)

    def _decode(self, raw_output: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        predictions = np.squeeze(raw_output)
        if predictions.ndim != 2:
            raise RuntimeError(f"Unsupported ONNX detection output shape: {raw_output.shape}")

        # YOLOv10 end-to-end output: x1, y1, x2, y2, confidence, class.
        if predictions.shape[1] == 6:
            boxes = predictions[:, :4].astype(np.float32)
            scores = predictions[:, 4].astype(np.float32)
            class_ids = predictions[:, 5].astype(np.int64)
            keep = scores >= self.confidence
            return boxes[keep], scores[keep], class_ids[keep]

        class_count = len(self.names)
        if predictions.shape[0] in {class_count + 4, class_count + 5}:
            predictions = predictions.T
        if predictions.shape[1] == class_count + 4:
            class_scores = predictions[:, 4:]
        elif predictions.shape[1] == class_count + 5:
            class_scores = predictions[:, 5:] * predictions[:, 4:5]
        else:
            raise RuntimeError(
                f"Cannot decode ONNX output {raw_output.shape} for {class_count} classes"
            )

        class_ids = np.argmax(class_scores, axis=1).astype(np.int64)
        scores = class_scores[np.arange(len(class_scores)), class_ids].astype(np.float32)
        keep = scores >= self.confidence
        xywh = predictions[keep, :4].astype(np.float32)
        scores = scores[keep]
        class_ids = class_ids[keep]
        boxes = np.empty_like(xywh)
        boxes[:, 0] = xywh[:, 0] - xywh[:, 2] / 2.0
        boxes[:, 1] = xywh[:, 1] - xywh[:, 3] / 2.0
        boxes[:, 2] = xywh[:, 0] + xywh[:, 2] / 2.0
        boxes[:, 3] = xywh[:, 1] + xywh[:, 3] / 2.0
        selected = self._class_aware_nms(boxes, scores, class_ids)
        return boxes[selected], scores[selected], class_ids[selected]

    def _class_aware_nms(
        self,
        boxes: np.ndarray,
        scores: np.ndarray,
        class_ids: np.ndarray,
    ) -> np.ndarray:
        selected: list[int] = []
        for class_id in np.unique(class_ids):
            indices = np.flatnonzero(class_ids == class_id)
            xywh = np.column_stack(
                (
                    boxes[indices, 0],
                    boxes[indices, 1],
                    boxes[indices, 2] - boxes[indices, 0],
                    boxes[indices, 3] - boxes[indices, 1],
                )
            ).tolist()
            keep = cv2.dnn.NMSBoxes(xywh, scores[indices].tolist(), self.confidence, self.iou)
            selected.extend(indices[np.asarray(keep).reshape(-1)].tolist())
        return np.asarray(sorted(selected, key=lambda index: scores[index], reverse=True), dtype=int)

    def predict(self, image_rgb: np.ndarray) -> list[Detection]:
        tensor, ratio, pad_x, pad_y = self._preprocess(image_rgb)
        outputs = self.session.run(self.output_names, {self.input_name: tensor})
        boxes, scores, class_ids = self._decode(outputs[0])
        height, width = image_rgb.shape[:2]
        detections: list[Detection] = []
        for box, score, class_id in zip(boxes, scores, class_ids, strict=True):
            x1 = (float(box[0]) - pad_x) / ratio
            y1 = (float(box[1]) - pad_y) / ratio
            x2 = (float(box[2]) - pad_x) / ratio
            y2 = (float(box[3]) - pad_y) / ratio
            try:
                bbox = BoundingBox(x1, y1, x2, y2).clipped(width, height)
            except ValueError:
                continue
            detections.append(
                Detection(
                    class_id=int(class_id),
                    label=self.names.get(int(class_id), f"class_{int(class_id)}"),
                    confidence=float(score),
                    bbox=bbox,
                )
            )
        return detections


def create_detector(
    model_path: str | Path,
    *,
    classes_path: str | Path | None = None,
    confidence: float = 0.25,
    iou: float = 0.60,
    image_size: int = 640,
    device: str | int | None = None,
) -> Detector:
    if Path(model_path).suffix.casefold() == ".onnx":
        return OnnxYoloDetector(
            model_path,
            classes_path=classes_path,
            confidence=confidence,
            iou=iou,
            image_size=image_size,
            device=device,
        )
    return UltralyticsDetector(
        model_path,
        confidence=confidence,
        iou=iou,
        image_size=image_size,
        device=device,
    )
