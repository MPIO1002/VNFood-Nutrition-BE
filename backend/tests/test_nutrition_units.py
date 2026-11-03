"""
Unit tests for weight / height unit support in MetabolismRequest.

These tests import only the Pydantic model (no FastAPI app / heavy CV deps),
so they run quickly without any mock setup.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from pydantic import ValidationError

from calcucalo.api.nutrition_meals import (
    MetabolismRequest,
    WeightUnit,
    HeightUnit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = dict(
    sex_for_equation="male",
    age=25,
    activity_level="moderate",
    goal="maintain_weight",
)


def _make(**overrides) -> MetabolismRequest:
    return MetabolismRequest(**{**_BASE, **overrides})


# ---------------------------------------------------------------------------
# Weight unit tests
# ---------------------------------------------------------------------------


class TestWeightUnit:
    def test_legacy_weight_kg_accepted(self):
        r = _make(weight_kg=70.0, height_cm=175.0)
        assert r._resolved_weight_kg == pytest.approx(70.0)

    def test_weight_kg_unit_default(self):
        r = _make(weight=80.0, height_cm=175.0)
        assert r._resolved_weight_kg == pytest.approx(80.0)
        assert r.weight_unit == WeightUnit.KG

    def test_weight_lbs_converted_correctly(self):
        # 132 lbs * 0.453592 = 59.874 kg
        r = _make(weight=132.0, weight_unit="lbs", height_cm=165.0, sex_for_equation="female")
        assert r._resolved_weight_kg == pytest.approx(59.874, abs=0.01)

    def test_weight_lbs_boundary_low(self):
        """55.12 lbs ≈ 25.0 kg — edge of valid range."""
        r = _make(weight=55.12, weight_unit="lbs", height_cm=165.0, sex_for_equation="female")
        assert r._resolved_weight_kg == pytest.approx(25.0, abs=0.1)

    def test_weight_lbs_too_light(self):
        """50 lbs ≈ 22.7 kg — below 25 kg minimum."""
        with pytest.raises(ValidationError, match="Resolved weight"):
            _make(weight=50.0, weight_unit="lbs", height_cm=165.0, sex_for_equation="female")

    def test_weight_lbs_too_heavy(self):
        """900 lbs ≈ 408 kg — above 400 kg maximum."""
        with pytest.raises(ValidationError, match="Resolved weight"):
            _make(weight=900.0, weight_unit="lbs", height_cm=175.0)

    def test_dual_weight_fields_rejected(self):
        """Sending both weight_kg (legacy) and weight (new) must be rejected."""
        with pytest.raises(ValidationError, match="weight_kg.*weight|weight.*weight_kg"):
            _make(weight_kg=70.0, weight=70.0, height_cm=175.0)

    def test_no_weight_field_rejected(self):
        """Omitting both weight_kg and weight must raise a clear error."""
        with pytest.raises(ValidationError):
            _make(height_cm=175.0)

    def test_invalid_weight_unit_rejected(self):
        with pytest.raises(ValidationError):
            _make(weight=70.0, weight_unit="stone", height_cm=175.0)


# ---------------------------------------------------------------------------
# Height unit tests
# ---------------------------------------------------------------------------


class TestHeightUnit:
    def test_legacy_height_cm_accepted(self):
        r = _make(weight_kg=70.0, height_cm=175.0)
        assert r._resolved_height_cm == pytest.approx(175.0)

    def test_height_cm_unit_default(self):
        r = _make(weight_kg=70.0, height=180.0)
        assert r._resolved_height_cm == pytest.approx(180.0)
        assert r.height_unit == HeightUnit.CM

    def test_height_ft_converted_correctly(self):
        # 5.74 ft * 30.48 = 174.954 cm
        r = _make(weight_kg=70.0, height=5.74, height_unit="ft")
        assert r._resolved_height_cm == pytest.approx(174.95, abs=0.1)

    def test_height_ft_common_values(self):
        # 6 ft = 182.88 cm
        r = _make(weight_kg=70.0, height=6.0, height_unit="ft")
        assert r._resolved_height_cm == pytest.approx(182.88, abs=0.01)

    def test_height_ft_too_short(self):
        """3.0 ft = 91.44 cm — below 100 cm minimum."""
        with pytest.raises(ValidationError, match="Resolved height"):
            _make(weight_kg=70.0, height=3.0, height_unit="ft")

    def test_height_ft_too_tall(self):
        """9 ft = 274.32 cm — above 250 cm maximum."""
        with pytest.raises(ValidationError, match="Resolved height"):
            _make(weight_kg=70.0, height=9.0, height_unit="ft")

    def test_dual_height_fields_rejected(self):
        """Sending both height_cm (legacy) and height (new) must be rejected."""
        with pytest.raises(ValidationError, match="height_cm.*height|height.*height_cm"):
            _make(weight_kg=70.0, height_cm=175.0, height=175.0)

    def test_no_height_field_rejected(self):
        """Omitting both height_cm and height must raise a clear error."""
        with pytest.raises(ValidationError):
            _make(weight_kg=70.0)

    def test_invalid_height_unit_rejected(self):
        with pytest.raises(ValidationError):
            _make(weight_kg=70.0, height=175.0, height_unit="inch")


# ---------------------------------------------------------------------------
# Combined / goal-pace consistency (regression)
# ---------------------------------------------------------------------------


class TestGoalPaceConsistency:
    def test_maintain_weight_no_pace(self):
        r = _make(weight_kg=70.0, height_cm=175.0)
        assert r.goal_pace is None

    def test_maintain_weight_with_pace_rejected(self):
        with pytest.raises(ValidationError, match="goal_pace"):
            _make(weight_kg=70.0, height_cm=175.0, goal_pace="standard")

    def test_lose_weight_with_pace(self):
        r = MetabolismRequest(
            sex_for_equation="male",
            age=25,
            weight_kg=80.0,
            height_cm=175.0,
            activity_level="moderate",
            goal="lose_weight",
            goal_pace="standard",
            weight_change_kg=5.0,
        )
        assert r._resolved_weight_kg == pytest.approx(80.0)
        assert r._resolved_height_cm == pytest.approx(175.0)

    def test_mixed_units_lose_weight(self):
        """lbs + ft with lose_weight goal."""
        r = MetabolismRequest(
            sex_for_equation="male",
            age=30,
            weight=176.0,
            weight_unit="lbs",
            height=5.9,
            height_unit="ft",
            activity_level="light",
            goal="lose_weight",
            goal_pace="gradual",
            weight_change_kg=3.0,
        )
        # 176 lbs ≈ 79.83 kg;  5.9 ft ≈ 179.83 cm
        assert r._resolved_weight_kg == pytest.approx(79.83, abs=0.1)
        assert r._resolved_height_cm == pytest.approx(179.83, abs=0.5)

