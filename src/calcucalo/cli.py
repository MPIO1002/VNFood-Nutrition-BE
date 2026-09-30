from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import FoodImageAnalyzer
from .dataset import audit_vietfood67, prepare_vietfood67
from .detector import create_detector
from .image_io import load_rgb_image
from .nutrition import NutritionCatalog
from .portion import PortionEstimator
from .segmenter import create_segmenter
from .visualize import save_overlay

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRIORS = PROJECT_ROOT / "configs" / "portion_priors.yaml"
DEFAULT_CLASSES = PROJECT_ROOT / "configs" / "vietfood67_classes.yaml"
DEFAULT_CATALOG = PROJECT_ROOT / "configs" / "food_catalog.json"


def _device(value: str) -> str | int:
    return int(value) if value.isdecimal() else value


def run_analyze(args: argparse.Namespace) -> int:
    device = _device(args.device) if args.device is not None else None
    detector = create_detector(
        args.model,
        classes_path=args.classes,
        confidence=args.confidence,
        iou=args.iou,
        image_size=args.image_size,
        device=device,
    )
    segmenter = create_segmenter(args.segmenter, sam_model=args.sam_model, device=device)
    component_detector = detector
    if args.component_pass:
        component_detector = create_detector(
            args.component_model or args.model,
            classes_path=args.classes,
            confidence=args.component_confidence,
            iou=args.component_iou,
            image_size=args.component_image_size,
            device=device,
        )
    estimator = PortionEstimator(args.priors)
    component_overrides = None
    if args.component_overrides:
        component_overrides = json.loads(
            Path(args.component_overrides).read_text(encoding="utf-8")
        )
    analyzer = FoodImageAnalyzer(
        detector,
        segmenter,
        estimator,
        nutrition_catalog=NutritionCatalog(args.catalog),
        component_detector=component_detector,
        enable_component_pass=args.component_pass,
        component_crop_padding=args.component_crop_padding,
        component_nms_iou=args.component_nms_iou,
        component_max_instances=args.component_max_instances,
    )
    result = analyzer.analyze(
        args.image,
        plate_diameter_cm=args.plate_diameter_cm,
        cm_per_pixel=args.cm_per_pixel,
        component_overrides=component_overrides,
    )
    output = (
        result.to_nutrition_dict(compact=True, unwrap_single=True)
        if args.json_format == "nutrition"
        else result.to_dict()
    )
    payload = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output_json:
        target = Path(args.output_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    if args.output_image:
        save_overlay(args.output_image, load_rgb_image(args.image), result)
    return 0


def run_prepare(args: argparse.Namespace) -> int:
    result = prepare_vietfood67(
        args.dataset_root,
        args.output,
        args.classes,
        validate=not args.skip_validation,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    has_errors = any(
        report[metric] > 0
        for report in result["splits"]
        for metric in (
            "missing_labels",
            "invalid_lines",
            "out_of_range_classes",
            "out_of_range_coordinates",
            "invalid_box_sizes",
            "orphan_labels",
        )
    )
    return 2 if has_errors else 0


def run_audit(args: argparse.Namespace) -> int:
    result = audit_vietfood67(
        args.dataset_root,
        args.classes,
        small_box_area_threshold=args.small_box_area_threshold,
        max_images_per_split=args.max_images_per_split,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"Audit report: {output}")
    else:
        print(payload)

    critical_fields = (
        "missing_labels",
        "invalid_lines",
        "out_of_range_classes",
        "out_of_range_coordinates",
        "invalid_box_sizes",
        "orphan_labels",
    )
    has_critical_errors = any(
        report[field] > 0 for report in result["splits"] for field in critical_fields
    )
    return 2 if has_critical_errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calcucalo", description="CalcuCalo vision pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze one food image")
    analyze.add_argument("image", help="Path to JPG/PNG/WebP image")
    analyze.add_argument("--model", required=True, help="YOLO .pt or .onnx weights")
    analyze.add_argument("--segmenter", choices=("sam", "grabcut", "bbox"), default="grabcut")
    analyze.add_argument("--sam-model", default="sam2.1_t.pt")
    analyze.add_argument("--classes", default=str(DEFAULT_CLASSES))
    analyze.add_argument("--priors", default=str(DEFAULT_PRIORS))
    analyze.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    analyze.add_argument(
        "--component-pass",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run a second high-resolution detector pass inside complex dishes (default: on)",
    )
    analyze.add_argument("--component-model", help="Optional component-specific YOLO weights")
    analyze.add_argument("--component-confidence", type=float, default=0.15)
    analyze.add_argument("--component-iou", type=float, default=0.50)
    analyze.add_argument("--component-image-size", type=int, default=960)
    analyze.add_argument("--component-crop-padding", type=float, default=0.08)
    analyze.add_argument("--component-nms-iou", type=float, default=0.50)
    analyze.add_argument("--component-max-instances", type=int, default=12)
    analyze.add_argument(
        "--component-overrides",
        help="JSON file mapping food_id to component grams from user corrections",
    )
    analyze.add_argument("--json-format", choices=("full", "nutrition"), default="full")
    analyze.add_argument(
        "--confidence",
        type=float,
        default=0.38,
        help="Dish confidence threshold; v5 validation F1 peaks near 0.384",
    )
    analyze.add_argument("--iou", type=float, default=0.60)
    analyze.add_argument("--image-size", type=int, default=640)
    analyze.add_argument("--device", help="cpu, mps or CUDA index such as 0")
    scale = analyze.add_mutually_exclusive_group()
    scale.add_argument("--plate-diameter-cm", type=float)
    scale.add_argument("--cm-per-pixel", type=float)
    analyze.add_argument("--output-json")
    analyze.add_argument("--output-image")
    analyze.set_defaults(handler=run_analyze)

    prepare = subparsers.add_parser("prepare-dataset", help="Validate VietFood67 and write data YAML")
    prepare.add_argument("dataset_root")
    prepare.add_argument("--output", default=str(PROJECT_ROOT / "configs" / "vietfood67.yaml"))
    prepare.add_argument("--classes", default=str(DEFAULT_CLASSES))
    prepare.add_argument("--skip-validation", action="store_true")
    prepare.set_defaults(handler=run_prepare)

    audit = subparsers.add_parser(
        "audit-dataset",
        help="Audit class balance, tiny boxes, duplicates and nested dish/component labels",
    )
    audit.add_argument("dataset_root")
    audit.add_argument("--classes", default=str(DEFAULT_CLASSES))
    audit.add_argument("--small-box-area-threshold", type=float, default=0.01)
    audit.add_argument(
        "--max-images-per-split",
        type=int,
        help="Optional quick-audit sample limit; omit for complete statistics",
    )
    audit.add_argument("--output", help="Optional JSON report path")
    audit.set_defaults(handler=run_audit)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
