from pathlib import Path

import yaml

from calcucalo.dataset import audit_vietfood67, prepare_vietfood67


def _make_split(root: Path, split: str) -> None:
    image_dir = root / split / "images"
    label_dir = root / split / "labels"
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    (image_dir / "sample.jpg").write_bytes(b"not-decoded-during-validation")
    (label_dir / "sample.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")


def test_prepare_discovers_valid_alias_and_writes_absolute_root(tmp_path: Path) -> None:
    _make_split(tmp_path, "train")
    _make_split(tmp_path, "valid")
    classes = tmp_path / "classes.yaml"
    classes.write_text("names:\n  0: Com\n", encoding="utf-8")
    output = tmp_path / "data.yaml"

    report = prepare_vietfood67(tmp_path, output, classes)
    data = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert report["classes"] == 1
    assert all(split["invalid_lines"] == 0 for split in report["splits"])
    assert data["path"] == tmp_path.resolve().as_posix()
    assert data["train"] == "train/images"
    assert data["val"] == "valid/images"


def test_audit_reports_small_duplicate_and_nested_annotations(tmp_path: Path) -> None:
    _make_split(tmp_path, "train")
    _make_split(tmp_path, "valid")
    (tmp_path / "train" / "labels" / "sample.txt").write_text(
        "0 0.5 0.5 0.8 0.8\n"
        "1 0.5 0.5 0.05 0.05\n"
        "1 0.5 0.5 0.05 0.05\n",
        encoding="utf-8",
    )
    classes = tmp_path / "classes.yaml"
    classes.write_text("names:\n  0: Mon chinh\n  1: Thanh phan\n", encoding="utf-8")

    report = audit_vietfood67(tmp_path, classes, small_box_area_threshold=0.01)
    train = next(split for split in report["splits"] if split["split"] == "train")

    assert train["instances"] == 2
    assert train["duplicate_labels"] == 1
    assert train["small_boxes"] == 1
    assert train["images_with_nested_labels"] == 1
    assert train["class_counts"] == {"0": 1, "1": 1}
    assert report["warnings"]
