"""Tests for profile, weight log and progress stats endpoints.

These tests use FastAPI TestClient and patch the repository / Cloudinary
service so they run without a real database or Cloudinary account.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from calcucalo.api.app import app
from calcucalo.api.auth import get_current_user
from calcucalo.api.profile_progress import get_profile_repo
from calcucalo.repositories.user_profile import UserNotFoundError

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FAKE_USER = {
    "id": 1,
    "email": "test@example.com",
    "full_name": "Test User",
    "is_active": True,
    "created_at": datetime(2025, 1, 1, 0, 0, 0),
}

FAKE_PROFILE = {
    "id": 1,
    "email": "test@example.com",
    "full_name": "Test User",
    "avatar_url": None,
    "gender": None,
    "sex_for_equation": None,
    "age": None,
    "height": None,
    "weight": None,
    "activity_level": None,
    "goal": None,
    "bmi": None,
    "tdee": None,
    "target_calories": None,
    "pregnant_or_breastfeeding": False,
    "competitive_athlete": False,
    "metabolism_affecting_condition": False,
    "is_active": True,
    "created_at": datetime(2025, 1, 1),
    "updated_at": datetime(2025, 1, 1),
}

FAKE_WEIGHT_LOG = {
    "id": 1,
    "user_id": 1,
    "weight_kg": 70.5,
    "recorded_at": datetime(2026, 10, 28, 8, 0, 0),
    "note": "Morning weigh-in",
}


@pytest.fixture()
def client():
    """TestClient with the current_user dependency overridden."""
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_repo():
    """Return a MagicMock standing in for UserProfileRepository."""
    repo = MagicMock()
    app.dependency_overrides[get_profile_repo] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_profile_repo, None)


# ---------------------------------------------------------------------------
# GET /api/v1/profile
# ---------------------------------------------------------------------------


def test_get_profile_ok(client, mock_repo):
    mock_repo.get_profile.return_value = FAKE_PROFILE
    resp = client.get("/api/v1/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    mock_repo.get_profile.assert_called_once_with(1)


def test_get_profile_not_found(client, mock_repo):
    mock_repo.get_profile.side_effect = UserNotFoundError("User 1 does not exist")
    resp = client.get("/api/v1/profile")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/profile
# ---------------------------------------------------------------------------


def test_update_profile_name(client, mock_repo):
    updated = {**FAKE_PROFILE, "full_name": "Updated Name"}
    mock_repo.update_profile.return_value = updated
    resp = client.patch("/api/v1/profile", json={"full_name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


def test_update_profile_avatar(client, mock_repo):
    url = "https://res.cloudinary.com/demo/image/upload/sample.jpg"
    updated = {**FAKE_PROFILE, "avatar_url": url}
    mock_repo.update_profile.return_value = updated
    resp = client.patch("/api/v1/profile", json={"avatar_url": url})
    assert resp.status_code == 200
    assert resp.json()["avatar_url"] == url


def test_update_profile_blank_name_rejected(client, mock_repo):
    resp = client.patch("/api/v1/profile", json={"full_name": "   "})
    assert resp.status_code == 422


def test_update_profile_empty_body_rejected(client, mock_repo):
    """Empty PATCH body must return 422 — nothing to update."""
    resp = client.patch("/api/v1/profile", json={})
    assert resp.status_code == 422


def test_update_profile_weight_only(client, mock_repo):
    """Sending only weight_kg triggers weight_history write and returns profile."""
    updated = {**FAKE_PROFILE, "weight": 65.0}
    mock_repo.update_profile.return_value = updated
    resp = client.patch("/api/v1/profile", json={"weight_kg": 65.0})
    assert resp.status_code == 200
    mock_repo.update_profile.assert_called_once()
    call_kwargs = mock_repo.update_profile.call_args.kwargs
    assert call_kwargs["weight_kg"] == 65.0


def test_update_profile_height_only(client, mock_repo):
    updated = {**FAKE_PROFILE, "height": 170.0}
    mock_repo.update_profile.return_value = updated
    resp = client.patch("/api/v1/profile", json={"height_cm": 170.0})
    assert resp.status_code == 200
    call_kwargs = mock_repo.update_profile.call_args.kwargs
    assert call_kwargs["height_cm"] == 170.0


def test_update_profile_goal_activity(client, mock_repo):
    updated = {**FAKE_PROFILE, "goal": "lose_weight", "activity_level": "moderate"}
    mock_repo.update_profile.return_value = updated
    resp = client.patch(
        "/api/v1/profile",
        json={"goal": "lose_weight", "activity_level": "moderate"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["goal"] == "lose_weight"
    assert data["activity_level"] == "moderate"


def test_update_profile_invalid_goal(client, mock_repo):
    resp = client.patch("/api/v1/profile", json={"goal": "fly_to_moon"})
    assert resp.status_code == 422


def test_update_profile_invalid_activity(client, mock_repo):
    resp = client.patch("/api/v1/profile", json={"activity_level": "super_active"})
    assert resp.status_code == 422


def test_update_profile_special_condition_stored(client, mock_repo):
    """Special-condition flags are accepted and forwarded to the repository."""
    updated = {**FAKE_PROFILE, "pregnant_or_breastfeeding": True}
    mock_repo.update_profile.return_value = updated
    resp = client.patch(
        "/api/v1/profile",
        json={"pregnant_or_breastfeeding": True},
    )
    assert resp.status_code == 200
    call_kwargs = mock_repo.update_profile.call_args.kwargs
    assert call_kwargs["pregnant_or_breastfeeding"] is True


def test_update_profile_age_out_of_range(client, mock_repo):
    resp = client.patch("/api/v1/profile", json={"age": 0})
    assert resp.status_code == 422


def test_update_profile_weight_too_heavy(client, mock_repo):
    resp = client.patch("/api/v1/profile", json={"weight_kg": 800})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/profile/weight
# ---------------------------------------------------------------------------


def test_add_weight_ok(client, mock_repo):
    mock_repo.add_weight_log.return_value = FAKE_WEIGHT_LOG
    resp = client.post(
        "/api/v1/profile/weight",
        json={"weight_kg": 70.5, "note": "Morning weigh-in"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["weight_kg"] == 70.5


def test_add_weight_invalid_zero(client, mock_repo):
    resp = client.post("/api/v1/profile/weight", json={"weight_kg": 0})
    assert resp.status_code == 422


def test_add_weight_too_heavy(client, mock_repo):
    resp = client.post("/api/v1/profile/weight", json={"weight_kg": 800})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/profile/weight/history
# ---------------------------------------------------------------------------


def test_weight_history_ok(client, mock_repo):
    mock_repo.get_weight_history.return_value = [FAKE_WEIGHT_LOG]
    resp = client.get("/api/v1/profile/weight/history?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    mock_repo.get_weight_history.assert_called_once_with(1, limit=5)


# ---------------------------------------------------------------------------
# GET /api/v1/progress/weekly
# ---------------------------------------------------------------------------

WEEKLY_ITEM = {
    "week_label": "2026-10-19 / 2026-10-25",
    "week_start": "2026-10-19",
    "week_end": "2026-10-25",
    "meal_count": 10,
    "days_logged": 5,
    "total_calories": 9500.0,
    "avg_daily_calories": 1900.0,
    "target_weekly_kcal": 14000.0,
    "adherence_pct": 67.9,
    "total_protein_g": 350.0,
    "total_fat_g": 210.0,
    "total_carb_g": 980.0,
}


def test_weekly_stats_ok(client, mock_repo):
    mock_repo.weekly_stats.return_value = [WEEKLY_ITEM]
    resp = client.get("/api/v1/progress/weekly?weeks=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["weeks"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["total_calories"] == 9500.0


def test_weekly_stats_invalid_weeks(client, mock_repo):
    resp = client.get("/api/v1/progress/weekly?weeks=0")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/progress/monthly
# ---------------------------------------------------------------------------

MONTHLY_ITEM = {
    "month_label": "2026-10",
    "month_start": "2026-10-01",
    "days_in_month": 31,
    "meal_count": 60,
    "days_logged": 20,
    "total_calories": 40000.0,
    "avg_daily_calories": 2000.0,
    "target_monthly_kcal": 62000.0,
    "adherence_pct": 64.5,
    "total_protein_g": 1400.0,
    "total_fat_g": 800.0,
    "total_carb_g": 4200.0,
}


def test_monthly_stats_ok(client, mock_repo):
    mock_repo.monthly_stats.return_value = [MONTHLY_ITEM]
    resp = client.get("/api/v1/progress/monthly?months=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["months"] == 1
    assert body["data"][0]["month_label"] == "2026-10"


def test_monthly_stats_max_exceeded(client, mock_repo):
    resp = client.get("/api/v1/progress/monthly?months=25")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/upload/image  (Cloudinary mocked)
# ---------------------------------------------------------------------------


def test_upload_image_ok(client):
    fake_url = "https://res.cloudinary.com/demo/image/upload/calcucalo/test.jpg"
    with (
        patch(
            "calcucalo.api.profile_progress.cloudinary_is_configured", return_value=True
        ),
        patch(
            "calcucalo.api.profile_progress.upload_image", return_value=fake_url
        ),
    ):
        resp = client.post(
            "/api/v1/upload/image",
            files={"image": ("photo.jpg", b"\xff\xd8\xff" + b"\x00" * 100, "image/jpeg")},
        )
    assert resp.status_code == 201
    assert resp.json()["url"] == fake_url


def test_upload_image_not_configured(client):
    with patch(
        "calcucalo.api.profile_progress.cloudinary_is_configured", return_value=False
    ):
        resp = client.post(
            "/api/v1/upload/image",
            files={"image": ("photo.jpg", b"\xff\xd8\xff" + b"\x00" * 100, "image/jpeg")},
        )
    assert resp.status_code == 503


def test_upload_image_wrong_type(client):
    with patch(
        "calcucalo.api.profile_progress.cloudinary_is_configured", return_value=True
    ):
        resp = client.post(
            "/api/v1/upload/image",
            files={"image": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert resp.status_code == 415
