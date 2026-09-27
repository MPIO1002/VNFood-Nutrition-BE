from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def parse_batch(value: str) -> int | float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch must be an integer, -1, or a fraction") from exc
    return int(parsed) if parsed.is_integer() else parsed


def unit_interval(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train, continue or fine-tune YOLO detection on VietFood67"
    )
    parser.add_argument("--data", required=True, help="Prepared VietFood67 data YAML")
    parser.add_argument("--model", default="yolo11n.pt", help="Base .pt weights or model YAML")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--batch", type=parse_batch, default=-1, help="-1 enables AutoBatch")
    parser.add_argument("--device", default=None, help="cpu, mps, 0 or CUDA indices")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--fraction", type=unit_interval, default=1.0)
    parser.add_argument(
        "--mosaic",
        type=unit_interval,
        default=1.0,
        help="Mosaic probability; use 0 for already-collaged data",
    )
    parser.add_argument("--close-mosaic", type=int, default=10)
    parser.add_argument(
        "--multi-scale",
        type=unit_interval,
        default=0.0,
        help="Ultralytics multi-scale range; 0 disables it",
    )
    parser.add_argument("--learning-rate", type=float, help="Override lr0")
    parser.add_argument(
        "--final-learning-rate-factor",
        type=float,
        help="Override lrf (final learning rate = lr0 * lrf)",
    )
    parser.add_argument("--warmup-epochs", type=float, help="Override warmup epochs")
    parser.add_argument("--save-period", type=int, default=1)
    parser.add_argument("--project", default="runs/detect")
    parser.add_argument("--name", default="vietfood67_yolo11n")
    parser.add_argument("--exist-ok", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted run from last.pt with its original optimizer/config",
    )
    mode.add_argument(
        "--fine-tune",
        action="store_true",
        help="Start a new phase from --model weights; --epochs means additional epochs",
    )
    parser.add_argument(
        "--test-after-training",
        action="store_true",
        help="Evaluate best.pt on the YAML test split and write test_metrics.json",
    )
    parser.add_argument("--test-project", help="Defaults to a sibling runs/val directory")
    parser.add_argument("--test-name", help="Defaults to <name>_test")
    parser.add_argument("--export-onnx", action="store_true")
    return parser


def resolve_save_dir(model: object, results: object) -> Path:
    """Resolve the Ultralytics run directory across single- and multi-GPU returns."""
    result_save_dir = getattr(results, "save_dir", None)
    if result_save_dir:
        return Path(result_save_dir)

    trainer = getattr(model, "trainer", None)
    trainer_save_dir = getattr(trainer, "save_dir", None)
    if trainer_save_dir:
        return Path(trainer_save_dir)

    raise RuntimeError(
        "Training finished but the output directory could not be resolved from "
        "either results.save_dir or model.trainer.save_dir."
    )


def _read_dataset_config(path: str | Path) -> dict[str, object]:
    with Path(path).open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"Dataset YAML must contain an object: {path}")
    return payload


def _class_count(payload: dict[str, object]) -> int:
    names = payload.get("names", {})
    return len(names) if isinstance(names, (dict, list)) else 0


def _checkpoint_is_completed(model: object) -> bool:
    checkpoint = getattr(model, "ckpt", None) or {}
    return checkpoint.get("epoch") == -1 and checkpoint.get("optimizer") is None


def _json_metrics(results: object) -> dict[str, object]:
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


def main() -> int:
    args = build_parser().parse_args()
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Install training dependencies with: pip install -e '.[inference]'") from exc

    if not Path(args.data).is_file():
        raise SystemExit(f"Dataset YAML not found: {args.data}")

    dataset_config = _read_dataset_config(args.data)
    if args.test_after_training and not dataset_config.get("test"):
        raise SystemExit("--test-after-training requires a 'test' split in the dataset YAML")
    if args.fine_tune and not Path(args.model).is_file():
        raise SystemExit("--fine-tune requires --model to point to an existing local .pt file")

    model = YOLO(args.model)
    expected_classes = _class_count(dataset_config)
    model_classes = len(getattr(model, "names", {}) or {})
    if (args.fine_tune or args.resume) and expected_classes != model_classes:
        raise SystemExit(
            f"Checkpoint has {model_classes} classes but dataset YAML defines "
            f"{expected_classes}. Refusing to continue with a mismatched class map."
        )

    if args.resume:
        if _checkpoint_is_completed(model):
            raise SystemExit(
                "This checkpoint belongs to a completed run and cannot be resumed exactly. "
                "Use --fine-tune with --epochs set to the number of additional epochs."
            )
        results = model.train(resume=True)
    else:
        train_options: dict[str, object] = {
            "data": args.data,
            "epochs": args.epochs,
            "imgsz": args.image_size,
            "batch": args.batch,
            "device": args.device,
            "workers": args.workers,
            "patience": args.patience,
            "fraction": args.fraction,
            "mosaic": args.mosaic,
            "close_mosaic": args.close_mosaic,
            "multi_scale": args.multi_scale,
            "save_period": args.save_period,
            "project": args.project,
            "name": args.name,
            "exist_ok": args.exist_ok,
            "pretrained": True,
            "plots": True,
            "seed": 42,
            "deterministic": True,
        }
        if args.fine_tune:
            train_options["lr0"] = (
                args.learning_rate if args.learning_rate is not None else 0.001
            )
            train_options["lrf"] = (
                args.final_learning_rate_factor
                if args.final_learning_rate_factor is not None
                else 0.1
            )
            train_options["warmup_epochs"] = (
                args.warmup_epochs if args.warmup_epochs is not None else 1.0
            )
            print(
                f"Fine-tune phase: {args.epochs} additional epochs from {args.model}. "
                "Epoch numbering starts again at 1 in the new run."
            )
        else:
            if args.learning_rate is not None:
                train_options["lr0"] = args.learning_rate
            if args.final_learning_rate_factor is not None:
                train_options["lrf"] = args.final_learning_rate_factor
            if args.warmup_epochs is not None:
                train_options["warmup_epochs"] = args.warmup_epochs
        results = model.train(**train_options)

    save_dir = resolve_save_dir(model, results)
    best = save_dir / "weights" / "best.pt"
    print(f"Training output: {save_dir}")
    print(f"Best checkpoint: {best}")
    if not best.is_file():
        raise RuntimeError(f"Training completed but best checkpoint is missing: {best}")

    if args.test_after_training:
        test_project = args.test_project or str(Path(args.project).parent / "val")
        test_name = args.test_name or f"{args.name}_test"
        test_device = args.device.split(",", 1)[0] if "," in str(args.device) else args.device
        validation = YOLO(str(best)).val(
            data=args.data,
            split="test",
            imgsz=args.image_size,
            batch=args.batch,
            device=test_device,
            workers=args.workers,
            plots=True,
            project=test_project,
            name=test_name,
        )
        test_report = save_dir / "test_metrics.json"
        test_report.write_text(
            json.dumps(_json_metrics(validation), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Test metrics: {test_report}")

    if args.export_onnx and best.is_file():
        exported = YOLO(str(best)).export(format="onnx", dynamic=True, simplify=True)
        print(f"Exported ONNX: {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
