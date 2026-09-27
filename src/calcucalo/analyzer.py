from __future__ import annotations

import numpy as np

from .calibration import PlateScaleEstimator, manual_scale
from .detector import Detector
from .domain import (
    AnalysisItem,
    AnalysisResult,
    BoundingBox,
    Detection,
    PortionEstimate,
    ScaleCalibration,
)
from .image_io import ImageInput, load_rgb_image
from .masks import bbox_mask, mask_quality, mask_to_polygons, normalize_mask
from .nutrition import ComponentEvidence, NutritionCatalog, normalize_food_name
from .portion import PortionEstimator
from .quality import assess_image_quality
from .segmenter import Segmenter


class FoodImageAnalyzer:
    def __init__(
        self,
        detector: Detector,
        segmenter: Segmenter,
        portion_estimator: PortionEstimator,
        nutrition_catalog: NutritionCatalog | None = None,
        component_detector: Detector | None = None,
        enable_component_pass: bool = False,
        component_crop_padding: float = 0.08,
        component_nms_iou: float = 0.50,
        component_max_instances: int = 12,
        exclude_class_ids: set[int] | None = None,
    ) -> None:
        if not 0.0 <= component_crop_padding <= 0.50:
            raise ValueError("component_crop_padding must be between 0 and 0.50")
        if not 0.0 < component_nms_iou <= 1.0:
            raise ValueError("component_nms_iou must be between 0 and 1")
        if component_max_instances <= 0:
            raise ValueError("component_max_instances must be positive")
        self.detector = detector
        self.segmenter = segmenter
        self.portion_estimator = portion_estimator
        self.nutrition_catalog = nutrition_catalog
        self.component_detector = component_detector or detector
        self.enable_component_pass = enable_component_pass
        self.component_crop_padding = component_crop_padding
        self.component_nms_iou = component_nms_iou
        self.component_max_instances = component_max_instances
        self.exclude_class_ids = exclude_class_ids if exclude_class_ids is not None else {27}
        self.plate_scale_estimator = PlateScaleEstimator()

    def analyze(
        self,
        source: ImageInput,
        *,
        plate_diameter_cm: float | None = None,
        cm_per_pixel: float | None = None,
        component_overrides: dict[str, dict[str, float]] | None = None,
    ) -> AnalysisResult:
        if component_overrides is not None and (
            not isinstance(component_overrides, dict)
            or any(
                not isinstance(components, dict) for components in component_overrides.values()
            )
        ):
            raise ValueError(
                "component_overrides must map food_id to an object of component grams"
            )
        image = load_rgb_image(source)
        height, width = image.shape[:2]
        image_quality = assess_image_quality(image)
        detections = [
            detection
            for detection in self.detector.predict(image)
            if detection.class_id not in self.exclude_class_ids
        ]
        if self.enable_component_pass and self.nutrition_catalog is not None:
            detections.extend(self._detect_nested_components(image, detections))

        calibration: ScaleCalibration | None = None
        warnings: list[str] = [
            recommendation
            for recommendation in image_quality["recommendations"]
            if image_quality["issues"] and recommendation
        ]
        if cm_per_pixel is not None:
            calibration = manual_scale(cm_per_pixel)
        elif plate_diameter_cm is not None:
            calibration = self.plate_scale_estimator.estimate(image, plate_diameter_cm)
            if calibration is None:
                warnings.append(
                    "Không tìm thấy đường tròn của đĩa/bát; khối lượng đang dùng khẩu phần mặc định."
                )
        else:
            warnings.append(
                "Ảnh không có tỷ lệ mét; khối lượng chỉ là khẩu phần mặc định. "
                "Hãy gửi cm_per_pixel hoặc plate_diameter_cm để ước lượng hình học."
            )

        missing = [detection for detection in detections if detection.mask is None]
        generated_masks = iter(self.segmenter.segment(image, missing)) if missing else iter(())

        items: list[AnalysisItem] = []
        for detection in detections:
            if detection.mask is None:
                try:
                    mask = next(generated_masks)
                except StopIteration:
                    mask = bbox_mask((height, width), detection.bbox)
            else:
                mask = detection.mask
            mask = normalize_mask(mask, (height, width))
            quality = mask_quality(mask, detection.bbox)
            portion = self.portion_estimator.estimate(
                detection.label,
                mask,
                calibration,
                mask_confidence=quality,
            )
            portion = self._apply_recipe_portion(detection.label, portion)
            items.append(
                AnalysisItem(
                    class_id=detection.class_id,
                    label=detection.label,
                    detection_confidence=detection.confidence,
                    bbox=detection.bbox,
                    polygons=mask_to_polygons(mask),
                    portion=portion,
                )
            )

        if not items:
            warnings.append("Không phát hiện món ăn nào vượt ngưỡng tin cậy.")
        elif self.nutrition_catalog is not None:
            self._attach_nutrition(items, warnings, component_overrides or {})
            composite_foods = [
                item.food
                for item in items
                if item.food is not None
                and item.component_of is None
                and self.nutrition_catalog.is_composite(item.label)
            ]
            catalog_only = [
                str(food["name"])
                for food in composite_foods
                if int(food.get("visual_components_matched", 0)) == 0
            ]
            if catalog_only:
                if self.enable_component_pass:
                    warnings.append(
                        "Không phát hiện trực tiếp thành phần nhỏ của: "
                        + ", ".join(catalog_only)
                        + "; dinh dưỡng hiện dùng tỷ lệ công thức mẫu."
                    )
                else:
                    warnings.append(
                        "Component pass đang tắt; thành phần của "
                        + ", ".join(catalog_only)
                        + " được suy ra từ công thức mẫu."
                    )
        return AnalysisResult(
            image_width=width,
            image_height=height,
            items=items,
            calibration=calibration,
            warnings=warnings,
            image_quality=image_quality,
        )

    def _detect_nested_components(
        self,
        image: np.ndarray,
        detections: list[Detection],
    ) -> list[Detection]:
        assert self.nutrition_catalog is not None
        image_height, image_width = image.shape[:2]
        nested: list[Detection] = []
        for parent in detections:
            if not self.nutrition_catalog.is_composite(parent.label):
                continue
            parent_box = parent.bbox.clipped(image_width, image_height)
            pad_x = parent_box.width * self.component_crop_padding
            pad_y = parent_box.height * self.component_crop_padding
            crop_box = BoundingBox(
                parent_box.x1 - pad_x,
                parent_box.y1 - pad_y,
                parent_box.x2 + pad_x,
                parent_box.y2 + pad_y,
            ).clipped(image_width, image_height)
            x1, y1 = int(crop_box.x1), int(crop_box.y1)
            x2, y2 = int(np.ceil(crop_box.x2)), int(np.ceil(crop_box.y2))
            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            candidates_by_ingredient: dict[str, list[Detection]] = {}
            for candidate in self.component_detector.predict(crop):
                if normalize_food_name(candidate.label) == normalize_food_name(parent.label):
                    continue
                ingredient_id = self.nutrition_catalog.match_component(parent.label, candidate.label)
                if ingredient_id is None:
                    continue
                global_box = BoundingBox(
                    candidate.bbox.x1 + x1,
                    candidate.bbox.y1 + y1,
                    candidate.bbox.x2 + x1,
                    candidate.bbox.y2 + y1,
                ).clipped(image_width, image_height)
                if not self._component_inside_parent(global_box, parent_box):
                    continue
                full_mask = None
                if candidate.mask is not None:
                    crop_mask = normalize_mask(candidate.mask, crop.shape[:2])
                    full_mask = np.zeros((image_height, image_width), dtype=bool)
                    full_mask[y1:y2, x1:x2] = crop_mask[: y2 - y1, : x2 - x1]
                mapped = Detection(
                    class_id=candidate.class_id,
                    label=candidate.label,
                    confidence=candidate.confidence,
                    bbox=global_box,
                    mask=full_mask,
                )
                candidates_by_ingredient.setdefault(ingredient_id, []).append(mapped)

            for ingredient_id, candidates in candidates_by_ingredient.items():
                for candidate in self._component_nms(candidates):
                    duplicate = any(
                        self.nutrition_catalog.match_component(parent.label, current.label)
                        == ingredient_id
                        and self._bbox_iou(candidate.bbox, current.bbox)
                        >= self.component_nms_iou
                        for current in [*detections, *nested]
                    )
                    if not duplicate:
                        nested.append(candidate)
        return nested

    @staticmethod
    def _component_inside_parent(child: BoundingBox, parent: BoundingBox) -> bool:
        child_area = child.width * child.height
        parent_area = parent.width * parent.height
        if child_area >= parent_area * 0.90:
            return False
        x1 = max(child.x1, parent.x1)
        y1 = max(child.y1, parent.y1)
        x2 = min(child.x2, parent.x2)
        y2 = min(child.y2, parent.y2)
        intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        return intersection / max(child_area, 1.0) >= 0.60

    @staticmethod
    def _bbox_iou(first: BoundingBox, second: BoundingBox) -> float:
        x1 = max(first.x1, second.x1)
        y1 = max(first.y1, second.y1)
        x2 = min(first.x2, second.x2)
        y2 = min(first.y2, second.y2)
        intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        union = first.width * first.height + second.width * second.height - intersection
        return intersection / max(union, 1.0)

    def _component_nms(self, candidates: list[Detection]) -> list[Detection]:
        kept: list[Detection] = []
        for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
            if any(
                self._bbox_iou(candidate.bbox, current.bbox) >= self.component_nms_iou
                for current in kept
            ):
                continue
            kept.append(candidate)
            if len(kept) >= self.component_max_instances:
                break
        return kept

    @staticmethod
    def _duplicates_existing(candidate: Detection, existing: list[Detection]) -> bool:
        for current in existing:
            if candidate.label.casefold() != current.label.casefold():
                continue
            x1 = max(candidate.bbox.x1, current.bbox.x1)
            y1 = max(candidate.bbox.y1, current.bbox.y1)
            x2 = min(candidate.bbox.x2, current.bbox.x2)
            y2 = min(candidate.bbox.y2, current.bbox.y2)
            intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            union = (
                candidate.bbox.width * candidate.bbox.height
                + current.bbox.width * current.bbox.height
                - intersection
            )
            if intersection / max(union, 1.0) >= 0.50:
                return True
        return False

    def _aggregate_component_evidence(
        self,
        candidates: list[tuple[AnalysisItem, ComponentEvidence]],
    ) -> ComponentEvidence:
        kept: list[tuple[AnalysisItem, ComponentEvidence]] = []
        for item, evidence in sorted(
            candidates,
            key=lambda candidate: candidate[1].confidence,
            reverse=True,
        ):
            if any(
                self._bbox_iou(item.bbox, current_item.bbox) >= self.component_nms_iou
                for current_item, _ in kept
            ):
                continue
            kept.append((item, evidence))
            if len(kept) >= self.component_max_instances:
                break

        best = max((evidence for _, evidence in kept), key=lambda item: item.confidence)
        metric_method = "mask_area_x_thickness_x_density"
        all_metric = all(evidence.method == metric_method for _, evidence in kept)
        return ComponentEvidence(
            label=best.label,
            weight_g=(
                sum(evidence.weight_g for _, evidence in kept)
                if all_metric
                else best.weight_g
            ),
            confidence=best.confidence,
            method=metric_method if all_metric else best.method,
            instance_count=len(kept),
            labels=tuple(evidence.label for _, evidence in kept),
        )

    def _apply_recipe_portion(
        self,
        label: str,
        portion: PortionEstimate,
    ) -> PortionEstimate:
        if self.nutrition_catalog is None or portion.method == "mask_area_x_thickness_x_density":
            return portion
        base_portion = self.nutrition_catalog.base_portion_for(label)
        if base_portion is None or portion.weight_g <= 0:
            return portion
        lower_ratio = portion.lower_g / portion.weight_g
        upper_ratio = portion.upper_g / portion.weight_g
        lower_g = base_portion * lower_ratio
        upper_g = base_portion * upper_ratio
        return PortionEstimate(
            weight_g=base_portion,
            lower_g=lower_g,
            upper_g=upper_g,
            method="recipe_base_portion_prior",
            confidence=portion.confidence,
            area_px=portion.area_px,
            assumptions=(
                *portion.assumptions,
                "Khối lượng dùng khẩu phần cơ sở của công thức vì ảnh chưa có tỷ lệ mét.",
            ),
            calculation={
                "model": "recipe_base_portion_prior",
                "is_depth_measured": False,
                "formula": "estimated_weight_g = recipe_base_portion_g",
                "range_formula": "range_g = recipe_base_portion_g * source_range_ratio",
                "inputs": {
                    "recipe_base_portion_g": round(base_portion, 4),
                    "source_method": portion.method,
                    "source_weight_g": round(portion.weight_g, 4),
                    "source_lower_g": round(portion.lower_g, 4),
                    "source_upper_g": round(portion.upper_g, 4),
                },
                "intermediate": {
                    "lower_ratio": round(lower_ratio, 6),
                    "upper_ratio": round(upper_ratio, 6),
                },
                "outputs": {
                    "estimated_weight_g": round(base_portion, 4),
                    "lower_g": round(lower_g, 4),
                    "upper_g": round(upper_g, 4),
                },
                "limitations": [
                    "The recipe portion is a catalog prior and was not measured from the image."
                ],
            },
        )

    @staticmethod
    def _mostly_inside(child: AnalysisItem, parent: AnalysisItem) -> bool:
        child_area = child.bbox.width * child.bbox.height
        parent_area = parent.bbox.width * parent.bbox.height
        if child_area >= parent_area * 0.90:
            return False
        intersection_width = max(
            0.0, min(child.bbox.x2, parent.bbox.x2) - max(child.bbox.x1, parent.bbox.x1)
        )
        intersection_height = max(
            0.0, min(child.bbox.y2, parent.bbox.y2) - max(child.bbox.y1, parent.bbox.y1)
        )
        return intersection_width * intersection_height / max(child_area, 1.0) >= 0.60

    def _attach_nutrition(
        self,
        items: list[AnalysisItem],
        warnings: list[str],
        component_overrides: dict[str, dict[str, float]],
    ) -> None:
        assert self.nutrition_catalog is not None
        evidence_by_parent: dict[int, dict[str, ComponentEvidence]] = {}
        parent_indices = [
            index
            for index, item in enumerate(items)
            if self.nutrition_catalog.is_composite(item.label)
        ]
        parent_indices.sort(key=lambda index: items[index].bbox.width * items[index].bbox.height)

        for parent_index in parent_indices:
            parent = items[parent_index]
            parent_food_id = self.nutrition_catalog.food_id_for(parent.label)
            if parent_food_id is None:
                continue
            component_candidates: dict[
                str, list[tuple[AnalysisItem, ComponentEvidence]]
            ] = {}
            for child_index, child in enumerate(items):
                if child_index == parent_index or child.component_of is not None:
                    continue
                if not self._mostly_inside(child, parent):
                    continue
                ingredient_id = self.nutrition_catalog.match_component(parent.label, child.label)
                if ingredient_id is None:
                    continue
                candidate = ComponentEvidence(
                    label=child.label,
                    weight_g=child.portion.weight_g,
                    confidence=child.detection_confidence,
                    method=child.portion.method,
                )
                component_candidates.setdefault(ingredient_id, []).append((child, candidate))
                child.component_of = parent_food_id
            evidence = {
                ingredient_id: self._aggregate_component_evidence(candidates)
                for ingredient_id, candidates in component_candidates.items()
            }
            evidence_by_parent[parent_index] = evidence

        missing_labels: list[str] = []
        for index, item in enumerate(items):
            food_id = self.nutrition_catalog.food_id_for(item.label)
            item.food = self.nutrition_catalog.analyze(
                item.label,
                estimated_portion_g=item.portion.weight_g,
                portion_method=item.portion.method,
                evidence=evidence_by_parent.get(index),
                component_overrides_g=component_overrides.get(food_id or ""),
            )
            if item.food is None and item.component_of is None:
                missing_labels.append(item.label)
        if missing_labels:
            warnings.append(
                "Chưa có công thức dinh dưỡng cho: " + ", ".join(sorted(set(missing_labels)))
            )
