from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from calcucalo.repositories.nutrition import NutritionCatalog
from calcucalo.services.analyzer import FoodImageAnalyzer
from calcucalo.services.detector import create_detector
from calcucalo.services.evaluation import EvaluationAccumulator
from calcucalo.services.portion import PortionEstimator
from calcucalo.services.segmenter import create_segmenter

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_manifest(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on manifest line {line_number}: {exc}") from exc
        if "image" not in record or "foods" not in record:
            raise ValueError(f"Manifest line {line_number} requires image and foods")
        records.append(record)
    return records


def parse_device(value: str | None) -> str | int | None:
    if value is None:
        return None
    return int(value) if value.isdecimal() else value


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate CalcuCalo on a weighed JSONL set")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--component-model")
    parser.add_argument("--component-pass", action="store_true")
    parser.add_argument("--segmenter", choices=("sam", "grabcut", "bbox"), default="grabcut")
    parser.add_argument("--sam-model", default="sam2.1_t.pt")
    parser.add_argument("--classes", default=PROJECT_ROOT / "configs" / "vietfood67_classes.yaml")
    parser.add_argument("--priors", default=PROJECT_ROOT / "configs" / "portion_priors.yaml")
    parser.add_argument("--catalog", default=PROJECT_ROOT / "configs" / "food_catalog.json")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.60)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    device = parse_device(args.device)
    detector = create_detector(
        args.model,
        classes_path=args.classes,
        confidence=args.confidence,
        iou=args.iou,
        image_size=args.image_size,
        device=device,
    )
    component_detector = detector
    if args.component_model:
        component_detector = create_detector(
            args.component_model,
            classes_path=args.classes,
            confidence=args.confidence,
            iou=args.iou,
            image_size=args.image_size,
            device=device,
        )
    analyzer = FoodImageAnalyzer(
        detector,
        create_segmenter(args.segmenter, sam_model=args.sam_model, device=device),
        PortionEstimator(args.priors),
        nutrition_catalog=NutritionCatalog(args.catalog),
        component_detector=component_detector,
        enable_component_pass=args.component_pass,
    )

    records = load_manifest(args.manifest)
    if args.limit is not None:
        records = records[: args.limit]
    accumulator = EvaluationAccumulator()
    manifest_dir = args.manifest.resolve().parent
    failed: list[dict[str, str]] = []
    for record in records:
        image_path = Path(record["image"])
        if not image_path.is_absolute():
            image_path = manifest_dir / image_path
        try:
            result = analyzer.analyze(
                image_path,
                plate_diameter_cm=record.get("plate_diameter_cm"),
                cm_per_pixel=record.get("cm_per_pixel"),
            )
            predicted = [item.food for item in result.items if item.food and not item.component_of]
            accumulator.add_sample(record["foods"], predicted)
        except (OSError, RuntimeError, ValueError) as exc:
            failed.append({"image": str(image_path), "error": str(exc)})

    report = accumulator.report()
    report["failed_samples"] = failed
    report["model"] = str(args.model)
    report["component_pass"] = args.component_pass
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
