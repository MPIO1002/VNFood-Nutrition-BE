from __future__ import annotations

from .calibration import PlateScaleEstimator, manual_scale
from .detector import Detector
from .domain import (
    AnalysisItem,
    AnalysisResult,
    PortionEstimate,
    ScaleCalibration,
)
from .image_io import ImageInput, load_rgb_image
from .masks import bbox_mask, mask_quality, mask_to_polygons, normalize_mask
from .nutrition import NutritionCatalog
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
        exclude_class_ids: set[int] | None = None,
    ) -> None:
        self.detector = detector
        self.segmenter = segmenter
        self.portion_estimator = portion_estimator
        self.nutrition_catalog = nutrition_catalog
        self.exclude_class_ids = exclude_class_ids if exclude_class_ids is not None else {27}
        self.plate_scale_estimator = PlateScaleEstimator()

    def analyze(
        self,
        source: ImageInput,
        *,
        plate_diameter_cm: float | None = None,
        container_type: str | None = None,
        container_length_cm: float | None = None,
        container_width_cm: float | None = None,
        cm_per_pixel: float | None = None,
    ) -> AnalysisResult:
        image = load_rgb_image(source)
        height, width = image.shape[:2]
        image_quality = assess_image_quality(image)
        detections = [
            detection
            for detection in self.detector.predict(image)
            if detection.class_id not in self.exclude_class_ids
        ]

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
                container_type=container_type,
                container_diameter_cm=plate_diameter_cm,
                container_length_cm=container_length_cm,
                container_width_cm=container_width_cm,
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
            self._attach_nutrition(items, warnings)

        return AnalysisResult(
            image_width=width,
            image_height=height,
            items=items,
            calibration=calibration,
            warnings=warnings,
            image_quality=image_quality,
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

    def _attach_nutrition(
        self,
        items: list[AnalysisItem],
        warnings: list[str],
    ) -> None:
        assert self.nutrition_catalog is not None
        missing_labels: list[str] = []
        for item in items:
            item.food = self.nutrition_catalog.analyze(
                item.label,
                estimated_portion_g=item.portion.weight_g,
                portion_method=item.portion.method,
            )
            if item.food is None:
                missing_labels.append(item.label)
        if missing_labels:
            warnings.append(
                "Chưa có công thức dinh dưỡng cho: " + ", ".join(sorted(set(missing_labels)))
            )
