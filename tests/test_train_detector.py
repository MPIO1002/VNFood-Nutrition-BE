from pathlib import Path
from types import SimpleNamespace

from scripts.train_detector import _checkpoint_is_completed, _json_metrics, resolve_save_dir


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
