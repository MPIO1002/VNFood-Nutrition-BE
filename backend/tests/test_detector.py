import numpy as np
import sys
import types

from calcucalo.services.detector import OnnxYoloDetector, UltralyticsDetector


def test_pt_checkpoint_reports_windows_torch_blocking(monkeypatch) -> None:
    fake_ultralytics = types.ModuleType("ultralytics")

    class BlockedYOLO:
        def __init__(self, _model_path: str) -> None:
            raise OSError(4551, "Application Control policy has blocked torch_python.dll")

    fake_ultralytics.YOLO = BlockedYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultralytics)

    try:
        UltralyticsDetector("best.pt")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected RuntimeError for blocked PyTorch checkpoint")

    assert "Application Control" in message
    assert "best.onnx" in message


def test_ultralytics_info_reports_incomplete_epoch_progress() -> None:
    detector = UltralyticsDetector.__new__(UltralyticsDetector)
    detector.model_path = "best.pt"
    detector.confidence = 0.25
    detector.iou = 0.6
    detector.image_size = 640
    detector.device = None
    detector.model = type(
        "FakeModel",
        (),
        {
            "names": {index: f"class_{index}" for index in range(68)},
            "task": "detect",
            "ckpt": {
                "epoch": 14,
                "optimizer": object(),
                "train_args": {"epochs": 20, "fraction": 1.0},
                "train_metrics": {"metrics/mAP50(B)": 0.7782},
            },
        },
    )()

    info = detector.info()

    assert info["training"]["completed_epochs"] == 15
    assert info["training"]["planned_epochs"] == 20
    assert info["training"]["training_complete"] is False


def test_decode_yolov10_end_to_end_output() -> None:
    detector = OnnxYoloDetector.__new__(OnnxYoloDetector)
    detector.confidence = 0.25
    detector.iou = 0.6
    detector.names = {0: "Com", 1: "Pho"}
    output = np.array(
        [[[10, 20, 30, 40, 0.9, 1], [5, 5, 15, 15, 0.1, 0]]],
        dtype=np.float32,
    )

    boxes, scores, class_ids = detector._decode(output)

    assert boxes.tolist() == [[10.0, 20.0, 30.0, 40.0]]
    assert scores.tolist() == [np.float32(0.9)]
    assert class_ids.tolist() == [1]
