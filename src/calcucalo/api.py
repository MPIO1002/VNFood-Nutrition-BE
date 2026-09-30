from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import UnidentifiedImageError

from .analyzer import FoodImageAnalyzer
from .detector import create_detector
from .nutrition import NutritionCatalog
from .portion import PortionEstimator
from .segmenter import create_segmenter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = Path(__file__).resolve().parent / "web"
EXPECTED_CLASS_COUNT = 68
app = FastAPI(title="CalcuCalo Vision API", version="0.5.1")
app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="assets")


def _model_path() -> tuple[Path | None, str]:
    configured = os.getenv("CALCUCALO_MODEL")
    if configured:
        return Path(configured).expanduser(), "environment"
    candidates = (
        PROJECT_ROOT / "models" / "best.onnx",
        PROJECT_ROOT / "models" / "best.pt",
        PROJECT_ROOT / "best.onnx",
        PROJECT_ROOT / "best.pt",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate, "auto_discovered"

    run_candidates: list[Path] = []
    for pattern in (
        "*/weights/best.onnx",
        "*/weights/best.pt",
        "runs/detect/*/weights/best.onnx",
        "runs/detect/*/weights/best.pt",
    ):
        run_candidates.extend(PROJECT_ROOT.glob(pattern))
    if run_candidates:
        latest = max(run_candidates, key=lambda path: path.stat().st_mtime_ns)
        return latest, "auto_discovered"
    return None, "missing"


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _model_readiness(info: dict[str, object]) -> dict[str, object]:
    class_count = int(info.get("class_count", 0) or 0)
    training = info.get("training") if isinstance(info.get("training"), dict) else {}
    metrics = info.get("metrics") if isinstance(info.get("metrics"), dict) else {}
    warnings: list[str] = []
    status = "unknown"

    if class_count != EXPECTED_CLASS_COUNT:
        status = "class_mismatch"
        warnings.append(
            f"Checkpoint có {class_count} lớp, trong khi pipeline VietFood67 mong đợi "
            f"{EXPECTED_CLASS_COUNT} lớp."
        )
    else:
        fraction = float(training.get("fraction", 1.0) or 1.0)
        planned_epochs = int(
            training.get("planned_epochs", training.get("epochs", 0)) or 0
        )
        completed_epochs = int(training.get("completed_epochs", 0) or 0)
        if fraction < 1.0 or (
            completed_epochs and completed_epochs <= 1
        ) or (not completed_epochs and planned_epochs and planned_epochs <= 1):
            status = "smoke_test"
            warnings.append(
                "Checkpoint chỉ là smoke test hoặc chưa dùng toàn bộ dữ liệu; không dùng để kết luận độ chính xác."
            )
        elif completed_epochs and planned_epochs and completed_epochs < planned_epochs:
            status = "training_incomplete"
            warnings.append(
                f"Checkpoint mới hoàn thành {completed_epochs}/{planned_epochs} epoch; "
                "hãy resume đến hết kế hoạch và đánh giá lại trên tập test độc lập."
            )
        elif metrics:
            map50 = float(metrics.get("metrics/mAP50(B)", 0.0) or 0.0)
            status = "candidate" if map50 >= 0.50 else "development"
            if map50 < 0.50:
                warnings.append("mAP50 lưu trong checkpoint còn dưới 0.50.")
        else:
            status = "unverified"
            warnings.append("Checkpoint không chứa metric để xác minh chất lượng.")

    detector_candidate = status == "candidate"
    if detector_candidate:
        warnings.append(
            "Detector đạt ngưỡng candidate; vẫn cần đánh giá end-to-end khối lượng và dinh dưỡng trước production."
        )

    return {
        "status": status,
        "expected_class_count": EXPECTED_CLASS_COUNT,
        "warnings": warnings,
        "detector_candidate": detector_candidate,
        "production_ready": False,
    }


@lru_cache(maxsize=1)
def get_analyzer() -> FoodImageAnalyzer:
    model_path, _ = _model_path()
    if model_path is None:
        raise RuntimeError(
            "Không tìm thấy model. Hãy đặt CALCUCALO_MODEL hoặc chép best.onnx/best.pt "
            "vào thư mục models hoặc thư mục gốc dự án."
        )
    if not model_path.is_file():
        raise RuntimeError(f"Model không tồn tại: {model_path}")
    device = os.getenv("CALCUCALO_DEVICE")
    segmenter_name = os.getenv("CALCUCALO_SEGMENTER", "grabcut")
    sam_model = os.getenv("CALCUCALO_SAM_MODEL", "sam2.1_t.pt")
    priors = os.getenv(
        "CALCUCALO_PORTION_PRIORS",
        str(PROJECT_ROOT / "configs" / "portion_priors.yaml"),
    )
    detector = create_detector(
        model_path,
        classes_path=PROJECT_ROOT / "configs" / "vietfood67_classes.yaml",
        confidence=_env_float("CALCUCALO_CONFIDENCE", 0.38, 0.01, 1.0),
        iou=_env_float("CALCUCALO_IOU", 0.60, 0.01, 1.0),
        image_size=_env_int("CALCUCALO_IMAGE_SIZE", 640, 160, 2048),
        device=device,
    )
    component_pass = os.getenv("CALCUCALO_COMPONENT_PASS", "true").casefold() in {
        "1",
        "true",
        "yes",
    }
    component_detector = detector
    component_model = os.getenv("CALCUCALO_COMPONENT_MODEL")
    if component_pass:
        component_detector = create_detector(
            component_model or model_path,
            classes_path=PROJECT_ROOT / "configs" / "vietfood67_classes.yaml",
            confidence=_env_float("CALCUCALO_COMPONENT_CONFIDENCE", 0.15, 0.01, 1.0),
            iou=_env_float("CALCUCALO_COMPONENT_IOU", 0.50, 0.01, 1.0),
            image_size=_env_int("CALCUCALO_COMPONENT_IMAGE_SIZE", 960, 160, 2048),
            device=device,
        )
    segmenter = create_segmenter(segmenter_name, sam_model=sam_model, device=device)
    catalog = os.getenv(
        "CALCUCALO_FOOD_CATALOG",
        str(PROJECT_ROOT / "configs" / "food_catalog.json"),
    )
    return FoodImageAnalyzer(
        detector,
        segmenter,
        PortionEstimator(priors),
        nutrition_catalog=NutritionCatalog(catalog),
        component_detector=component_detector,
        enable_component_pass=component_pass,
        component_crop_padding=_env_float(
            "CALCUCALO_COMPONENT_CROP_PADDING", 0.08, 0.0, 0.50
        ),
        component_nms_iou=_env_float("CALCUCALO_COMPONENT_NMS_IOU", 0.50, 0.01, 1.0),
        component_max_instances=_env_int(
            "CALCUCALO_COMPONENT_MAX_INSTANCES", 12, 1, 100
        ),
    )


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
def health() -> dict[str, object]:
    model_path, source = _model_path()
    return {
        "status": "ok",
        "model_configured": model_path is not None,
        "model_exists": bool(model_path and model_path.is_file()),
        "model_file": model_path.name if model_path else None,
        "model_source": source,
        "analyzer_loaded": get_analyzer.cache_info().currsize > 0,
    }


@app.get("/api/v1/model/info")
def model_info() -> dict[str, object]:
    try:
        analyzer = get_analyzer()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    detector_info = (
        analyzer.detector.info()
        if hasattr(analyzer.detector, "info")
        else {"backend": type(analyzer.detector).__name__}
    )
    component_detector_info = (
        analyzer.component_detector.info()
        if hasattr(analyzer.component_detector, "info")
        else {"backend": type(analyzer.component_detector).__name__}
    )
    model_path, source = _model_path()
    return {
        "api_version": app.version,
        "model_source": source,
        "model_exists": bool(model_path and model_path.is_file()),
        "detector": detector_info,
        "readiness": _model_readiness(detector_info),
        "pipeline": {
            "segmenter": type(analyzer.segmenter).__name__,
            "component_pass": analyzer.enable_component_pass,
            "component_detector": component_detector_info,
            "component_crop_padding": analyzer.component_crop_padding,
            "component_nms_iou": analyzer.component_nms_iou,
            "component_max_instances": analyzer.component_max_instances,
            "nutrition_catalog": analyzer.nutrition_catalog is not None,
            "portion_estimation": "metric_geometry_or_catalog_prior",
            "depth_measurement": False,
        },
    }


@app.post("/api/v1/food/analyze")
async def analyze_food(
    image: Annotated[UploadFile, File()],
    plate_diameter_cm: Annotated[float | None, Form()] = None,
    cm_per_pixel: Annotated[float | None, Form()] = None,
    response_format: Annotated[str, Form()] = "full",
    component_overrides_json: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    if plate_diameter_cm is not None and cm_per_pixel is not None:
        raise HTTPException(status_code=422, detail="Use only one scale calibration method")
    if response_format not in {"full", "nutrition"}:
        raise HTTPException(status_code=422, detail="response_format must be full or nutrition")
    component_overrides = None
    if component_overrides_json:
        try:
            component_overrides = json.loads(component_overrides_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Invalid component_overrides_json") from exc
        if not isinstance(component_overrides, dict):
            raise HTTPException(status_code=422, detail="component_overrides_json must be an object")
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=422, detail="Empty image")
    if len(payload) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 15 MB")
    try:
        analyzer = get_analyzer()
        result = analyzer.analyze(
            payload,
            plate_diameter_cm=plate_diameter_cm,
            cm_per_pixel=cm_per_pixel,
            component_overrides=component_overrides,
        )
    except (UnidentifiedImageError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if response_format == "nutrition":
        return result.to_nutrition_dict(compact=True, unwrap_single=True)
    return result.to_dict()
