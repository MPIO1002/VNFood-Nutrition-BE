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
        plate_area_px = None
        if cm_per_pixel is not None:
            calibration = manual_scale(cm_per_pixel)
        elif plate_diameter_cm is not None:
            calibration = self.plate_scale_estimator.estimate(image, plate_diameter_cm)
            if calibration is None:
                warnings.append(
                    "Không tìm thấy đường tròn của đĩa/bát; khối lượng đang dùng khẩu phần mặc định."
                )
            else:
                plate_area_px = 3.14159 * (calibration.reference["circle_xy_radius_px"][2])**2
        else:
            circle_result = self.plate_scale_estimator.detect_container_circle(image)
            if circle_result:
                plate_area_px = 3.14159 * circle_result[0][2]**2
            
            warnings.append(
                "Ảnh không có tỷ lệ mét; sử dụng phương pháp tỷ lệ lắp đầy (fill-ratio)."
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
                plate_area_px=plate_area_px,
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
        return portion

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
