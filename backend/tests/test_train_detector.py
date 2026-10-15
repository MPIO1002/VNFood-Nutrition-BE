from pathlib import Path
from types import SimpleNamespace

from scripts.train_detector import (
    _checkpoint_is_completed,
    _fine_tune_options,
    _json_metrics,
    build_parser,
    resolve_save_dir,
)


def test_completed_checkpoint_is_not_resumable() -> None:
    model = SimpleNamespace(ckpt={"epoch": -1, "optimizer": None})

    assert _checkpoint_is_completed(model) is True


def test_resolve_save_dir_supports_multi_gpu_return_shape(tmp_path: Path) -> None:
    model = SimpleNamespace(trainer=SimpleNamespace(save_dir=tmp_path))

    assert resolve_save_dir(model, {}) == tmp_path


def test_json_metrics_keeps_numbers_and_speed() -> None:
    results = SimpleNamespace(
        results_dict={"metrics/mAP50(B)": 0.75, "private": object()},
        speed={"inference": 6.5},
        save_dir="runs/val/example",
    )

    assert _json_metrics(results) == {
        "metrics/mAP50(B)": 0.75,
        "speed_ms": {"inference": 6.5},
        "save_dir": "runs/val/example",
    }


def test_fine_tune_uses_explicit_optimizer_and_requested_learning_rate() -> None:
    args = build_parser().parse_args(
        [
            "--data",
            "dataset.yaml",
            "--model",
            "best.pt",
            "--fine-tune",
            "--learning-rate",
            "0.0005",
        ]
    )

    assert _fine_tune_options(args) == {
        "optimizer": "SGD",
        "lr0": 0.0005,
        "lrf": 0.1,
        "warmup_epochs": 1.0,
    }
