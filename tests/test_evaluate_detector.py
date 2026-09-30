from pathlib import Path
from types import SimpleNamespace

from scripts.evaluate_detector import default_report_path, json_metrics


def test_default_report_is_written_next_to_training_artifacts(tmp_path: Path) -> None:
    checkpoint = tmp_path / "run" / "weights" / "best.pt"

    assert default_report_path(checkpoint, "test") == tmp_path / "run" / "test_metrics.json"


def test_evaluation_metrics_are_json_serializable() -> None:
    results = SimpleNamespace(
        results_dict={"metrics/mAP50-95(B)": 0.62579},
        speed={"inference": 6.5},
        save_dir="runs/val/v5_test",
    )

    assert json_metrics(results) == {
        "metrics/mAP50-95(B)": 0.62579,
        "speed_ms": {"inference": 6.5},
        "save_dir": "runs/val/v5_test",
    }
