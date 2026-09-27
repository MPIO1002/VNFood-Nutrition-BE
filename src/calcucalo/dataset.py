from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from random import Random
from typing import Any

import yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass
class SplitReport:
    split: str
    images: int = 0
    images_scanned: int = 0
    labels: int = 0
    missing_labels: int = 0
    empty_labels: int = 0
    invalid_lines: int = 0
    out_of_range_classes: int = 0
    out_of_range_coordinates: int = 0
    invalid_box_sizes: int = 0
    orphan_labels: int = 0
    instances: int = 0
    duplicate_labels: int = 0
    small_boxes: int = 0
    multi_class_images: int = 0
    images_with_nested_labels: int = 0
    nested_label_pairs: int = 0
    class_counts: dict[str, int] = field(default_factory=dict)
    small_box_counts: dict[str, int] = field(default_factory=dict)


def read_class_names(path: str | Path) -> dict[int, str]:
    with Path(path).open("r", encoding="utf-8") as stream:
        values = (yaml.safe_load(stream) or {}).get("names", {})
    if isinstance(values, list):
        names = dict(enumerate(map(str, values)))
    else:
        names = {int(key): str(value) for key, value in values.items()}
    if not names or sorted(names) != list(range(len(names))):
        raise ValueError("Class IDs must be contiguous and start at zero")
    return names


def _find_split(root: Path, split_names: tuple[str, ...]) -> tuple[Path, Path] | None:
    for split in split_names:
        candidates = (
            (root / split / "images", root / split / "labels"),
            (root / "images" / split, root / "labels" / split),
        )
        for image_dir, label_dir in candidates:
            if image_dir.is_dir() and label_dir.is_dir():
                return image_dir, label_dir
    return None


def discover_yolo_layout(root: str | Path) -> dict[str, tuple[Path, Path]]:
    root = Path(root).expanduser().resolve()
    layouts: dict[str, tuple[Path, Path]] = {}
    aliases = {
        "train": ("train", "training"),
        "val": ("val", "valid", "validation"),
        "test": ("test", "testing"),
    }
    for canonical, names in aliases.items():
        found = _find_split(root, names)
        if found:
            layouts[canonical] = found
    if "train" not in layouts or "val" not in layouts:
        raise FileNotFoundError(
            "Could not find YOLO train/val folders. Expected either "
            "<root>/train/images + labels or <root>/images/train + labels/train "
            "(valid/validation are accepted aliases for val)."
        )
    return layouts


def validate_split(
    split: str,
    image_dir: Path,
    label_dir: Path,
    number_of_classes: int,
    small_box_area_threshold: float = 0.01,
    max_images: int | None = None,
) -> SplitReport:
    report = SplitReport(split=split)
    all_images = [
        path for path in image_dir.rglob("*") if path.suffix.casefold() in IMAGE_SUFFIXES
    ]
    labels = list(label_dir.rglob("*.txt"))
    report.images = len(all_images)
    report.labels = len(labels)
    images = all_images
    if max_images is not None:
        if max_images <= 0:
            raise ValueError("max_images must be positive")
        images = (
            sorted(Random(42).sample(images, max_images))
            if len(images) > max_images
            else sorted(images)
        )
    report.images_scanned = len(images)

    label_by_relative_stem = {
        path.relative_to(label_dir).with_suffix("").as_posix().casefold(): path for path in labels
    }
    image_keys = {
        path.relative_to(image_dir).with_suffix("").as_posix().casefold() for path in all_images
    }
    report.orphan_labels = len(set(label_by_relative_stem) - image_keys)
    for image_path in images:
        key = image_path.relative_to(image_dir).with_suffix("").as_posix().casefold()
        label_path = label_by_relative_stem.get(key)
        if label_path is None:
            report.missing_labels += 1
            continue
        lines = [line.strip() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            report.empty_labels += 1
        seen_labels: set[tuple[float, ...]] = set()
        image_classes: set[int] = set()
        image_boxes: list[tuple[int, float, float, float, float]] = []
        for line in lines:
            try:
                values = [float(value) for value in line.split()]
            except (OverflowError, ValueError):
                report.invalid_lines += 1
                continue
            if len(values) < 5:
                report.invalid_lines += 1
                continue
            try:
                class_id = int(values[0])
            except (OverflowError, ValueError):
                report.invalid_lines += 1
                continue
            if values[0] != class_id or not 0 <= class_id < number_of_classes:
                report.out_of_range_classes += 1
                continue
            # Detection labels have xywh after class; segmentation labels have polygon xy pairs.
            coordinates = values[1:]
            if any(value < 0.0 or value > 1.0 for value in coordinates):
                report.out_of_range_coordinates += 1
                continue
            if len(values) != 5 and (len(coordinates) < 6 or len(coordinates) % 2 != 0):
                report.invalid_lines += 1
                continue

            normalized = tuple(round(value, 8) for value in values)
            if normalized in seen_labels:
                report.duplicate_labels += 1
                continue
            seen_labels.add(normalized)

            if len(values) == 5:
                center_x, center_y, width, height = coordinates
                if width <= 0.0 or height <= 0.0:
                    report.invalid_box_sizes += 1
                    continue
                x1, y1 = center_x - width / 2.0, center_y - height / 2.0
                x2, y2 = center_x + width / 2.0, center_y + height / 2.0
            else:
                x_values = coordinates[0::2]
                y_values = coordinates[1::2]
                x1, x2 = min(x_values), max(x_values)
                y1, y2 = min(y_values), max(y_values)
                width, height = x2 - x1, y2 - y1
                if width <= 0.0 or height <= 0.0:
                    report.invalid_box_sizes += 1
                    continue

            area = width * height
            class_key = str(class_id)
            report.instances += 1
            report.class_counts[class_key] = report.class_counts.get(class_key, 0) + 1
            image_classes.add(class_id)
            image_boxes.append((class_id, x1, y1, x2, y2))
            if area < small_box_area_threshold:
                report.small_boxes += 1
                report.small_box_counts[class_key] = (
                    report.small_box_counts.get(class_key, 0) + 1
                )

        if len(image_classes) > 1:
            report.multi_class_images += 1
        nested_pairs = _count_nested_pairs(image_boxes)
        if nested_pairs:
            report.images_with_nested_labels += 1
            report.nested_label_pairs += nested_pairs
    return report


def _count_nested_pairs(boxes: list[tuple[int, float, float, float, float]]) -> int:
    """Count different-class boxes that look like component-inside-dish labels."""
    count = 0
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            if first[0] == second[0]:
                continue
            first_area = max(0.0, first[3] - first[1]) * max(0.0, first[4] - first[2])
            second_area = max(0.0, second[3] - second[1]) * max(0.0, second[4] - second[2])
            if first_area <= 0.0 or second_area <= 0.0:
                continue
            smaller, larger = (first, second) if first_area < second_area else (second, first)
            smaller_area, larger_area = sorted((first_area, second_area))
            if smaller_area >= larger_area * 0.90:
                continue
            intersection_width = max(0.0, min(smaller[3], larger[3]) - max(smaller[1], larger[1]))
            intersection_height = max(0.0, min(smaller[4], larger[4]) - max(smaller[2], larger[2]))
            if intersection_width * intersection_height / smaller_area >= 0.60:
                count += 1
    return count


def audit_vietfood67(
    dataset_root: str | Path,
    classes_yaml: str | Path,
    small_box_area_threshold: float = 0.01,
    max_images_per_split: int | None = None,
) -> dict[str, Any]:
    """Return class balance, small-object and annotation-consistency diagnostics."""
    if not 0.0 < small_box_area_threshold <= 1.0:
        raise ValueError("small_box_area_threshold must be between 0 and 1")

    root = Path(dataset_root).expanduser().resolve()
    layouts = discover_yolo_layout(root)
    names = read_class_names(classes_yaml)
    reports = [
        validate_split(
            split,
            image_dir,
            label_dir,
            len(names),
            small_box_area_threshold=small_box_area_threshold,
            max_images=max_images_per_split,
        )
        for split, (image_dir, label_dir) in layouts.items()
    ]

    class_totals = {class_id: 0 for class_id in names}
    small_totals = {class_id: 0 for class_id in names}
    for report in reports:
        for class_id in names:
            class_totals[class_id] += report.class_counts.get(str(class_id), 0)
            small_totals[class_id] += report.small_box_counts.get(str(class_id), 0)

    nonzero_counts = [count for count in class_totals.values() if count > 0]
    imbalance_ratio = (
        max(nonzero_counts) / min(nonzero_counts) if len(nonzero_counts) > 1 else 1.0
    )
    warnings: list[str] = []
    duplicate_total = sum(report.duplicate_labels for report in reports)
    small_total = sum(report.small_boxes for report in reports)
    nested_images = sum(report.images_with_nested_labels for report in reports)
    if duplicate_total:
        warnings.append(
            f"Found {duplicate_total} duplicate annotation lines; remove them before final training."
        )
    if small_total:
        warnings.append(
            f"Found {small_total} boxes below normalized area {small_box_area_threshold:.4f}; "
            "review small-object recall and consider a larger training image size."
        )
    if imbalance_ratio >= 10.0:
        warnings.append(
            f"Class imbalance is high (largest/smallest non-empty class: {imbalance_ratio:.1f}x)."
        )
    if nested_images:
        warnings.append(
            f"Found {nested_images} images with different-class nested boxes; audit whether dish "
            "and component labels follow one consistent policy."
        )
    if max_images_per_split is not None:
        warnings.append(
            f"Audit used at most {max_images_per_split} images per split; omit the limit "
            "before publishing final dataset statistics."
        )

    class_summary = [
        {
            "class_id": class_id,
            "name": names[class_id],
            "instances": class_totals[class_id],
            "small_boxes": small_totals[class_id],
            "small_box_fraction": round(
                small_totals[class_id] / class_totals[class_id], 4
            )
            if class_totals[class_id]
            else None,
        }
        for class_id in names
    ]
    return {
        "dataset_root": str(root),
        "classes": len(names),
        "small_box_area_threshold": small_box_area_threshold,
        "max_images_per_split": max_images_per_split,
        "splits": [asdict(report) for report in reports],
        "class_summary": class_summary,
        "imbalance_ratio": round(imbalance_ratio, 3),
        "warnings": warnings,
    }


def prepare_vietfood67(
    dataset_root: str | Path,
    output_yaml: str | Path,
    classes_yaml: str | Path,
    validate: bool = True,
) -> dict[str, Any]:
    root = Path(dataset_root).expanduser().resolve()
    layouts = discover_yolo_layout(root)
    names = read_class_names(classes_yaml)
    output = Path(output_yaml).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {"path": root.as_posix(), "names": names}
    for split, (image_dir, _) in layouts.items():
        data[split] = image_dir.relative_to(root).as_posix()
    output.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    reports: list[dict[str, Any]] = []
    if validate:
        for split, (image_dir, label_dir) in layouts.items():
            reports.append(asdict(validate_split(split, image_dir, label_dir, len(names))))
    return {"dataset_yaml": str(output), "classes": len(names), "splits": reports}
