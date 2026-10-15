from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def parse_batch(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a completed YOLO detector without retraining it"
    )
    parser.add_argument("--data", required=True, help="Prepared dataset YAML")
    parser.add_argument("--model", required=True, help="Completed best.pt checkpoint")
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--batch", type=parse_batch, default=32)
    parser.add_argument("--device", default=None, help="cpu, mps or one CUDA index")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--project", default="runs/val")
    parser.add_argument("--name", default="detector_test")
    parser.add_argument("--output-json", help="Defaults to <training-run>/<split>_metrics.json")
    parser.add_argument("--export-onnx", action="store_true")
    return parser


def json_metrics(results: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in (getattr(results, "results_dict", None) or {}).items():
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, (int, float, str, bool)) or value is None:
            payload[str(key)] = value
    speed = getattr(results, "speed", None)
    if isinstance(speed, dict):
        payload["speed_ms"] = {
            str(key): float(value)
            for key, value in speed.items()
            if isinstance(value, (int, float))
        }
    save_dir = getattr(results, "save_dir", None)
    if save_dir:
        payload["save_dir"] = str(save_dir)
    return payload


def default_report_path(model_path: Path, split: str) -> Path:
    if model_path.parent.name == "weights":
        return model_path.parent.parent / f"{split}_metrics.json"
    return model_path.parent / f"{split}_metrics.json"


def main() -> int:
    args = build_parser().parse_args()
    data_path = Path(args.data)
    model_path = Path(args.model)
    if not data_path.is_file():
        raise SystemExit(f"Dataset YAML not found: {data_path}")
    if not model_path.is_file():
        raise SystemExit(f"Checkpoint not found: {model_path}")

    dataset = yaml.safe_load(data_path.read_text(encoding="utf-8")) or {}
    if not isinstance(dataset, dict) or not dataset.get(args.split):
        raise SystemExit(f"Dataset YAML does not define the '{args.split}' split")

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Install inference dependencies with: pip install -e '.[inference]'") from exc

    model = YOLO(str(model_path))
    results = model.val(
        data=str(data_path),
        split=args.split,
        imgsz=args.image_size,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        plots=True,
        project=args.project,
        name=args.name,
    )
    report_path = (
        Path(args.output_json)
        if args.output_json
        else default_report_path(model_path, args.split)
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(json_metrics(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Metrics: {report_path}")

    if args.export_onnx:
        exported = model.export(format="onnx", dynamic=True, simplify=True)
        print(f"Exported ONNX: {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
