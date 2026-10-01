import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

import calcucalo.api as api_module
from calcucalo.api import _model_path, _model_readiness, app




def test_model_path_finds_checkpoint_inside_training_run(tmp_path, monkeypatch) -> None:
    checkpoint = tmp_path / "vietfood67_yolo11n_v1" / "weights" / "best.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"test checkpoint")
    monkeypatch.delenv("CALCUCALO_MODEL", raising=False)
    monkeypatch.setattr(api_module, "PROJECT_ROOT", tmp_path)

    model_path, source = _model_path()

    assert model_path == checkpoint
    assert source == "auto_discovered"


def test_model_readiness_flags_fractional_smoke_test() -> None:
    readiness = _model_readiness(
        {
            "class_count": 68,
            "training": {"epochs": 1, "fraction": 0.01},
            "metrics": {"metrics/mAP50(B)": 0.00019},
        }
    )

    assert readiness["status"] == "smoke_test"
    assert readiness["detector_candidate"] is False
    assert readiness["production_ready"] is False
    assert readiness["warnings"]


def test_model_readiness_accepts_candidate_with_expected_classes() -> None:
    readiness = _model_readiness(
        {
            "class_count": 68,
            "training": {"epochs": 20, "fraction": 1.0},
            "metrics": {"metrics/mAP50(B)": 0.75},
        }
    )

    assert readiness == {
        "status": "candidate",
        "expected_class_count": 68,
        "warnings": [
            "Detector đạt ngưỡng candidate; vẫn cần đánh giá end-to-end khối lượng và dinh dưỡng trước production."
        ],
        "detector_candidate": True,
        "production_ready": False,
    }


def test_model_readiness_rejects_incomplete_training_run() -> None:
    readiness = _model_readiness(
        {
            "class_count": 68,
            "training": {
                "epochs": 20,
                "planned_epochs": 20,
                "completed_epochs": 15,
                "training_complete": False,
                "fraction": 1.0,
            },
            "metrics": {
                "metrics/mAP50(B)": 0.7782,
                "metrics/mAP50-95(B)": 0.6254,
            },
        }
    )

    assert readiness["status"] == "training_incomplete"
    assert readiness["detector_candidate"] is False
    assert readiness["production_ready"] is False
    assert "15/20 epoch" in readiness["warnings"][0]
