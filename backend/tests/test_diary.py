"""Tests for diary weekly/monthly photo-grid API."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from calcucalo.api.app import app
from calcucalo.api.auth import get_current_user
from calcucalo.api.diary import get_diary_repo

FAKE_USER = {
    "id": 1,
    "email": "test@example.com",
    "full_name": "Test User",
    "is_active": True,
    "created_at": datetime(2025, 1, 1),
}

# ---------------------------------------------------------------------------
# Shared dummy payloads matching DiaryRepository output shape
# ---------------------------------------------------------------------------

DUMMY_DAY_CELL = {
    "date": "2026-10-28",
    "has_meals": True,
    "meal_count": 2,
    "total_kcal": 850.0,
    "representative_image_url": "https://res.cloudinary.com/demo/image/upload/food.jpg",
}

DUMMY_DAY_CELL_EMPTY = {
    "date": "2026-10-27",
    "has_meals": False,
    "meal_count": 0,
    "total_kcal": 0.0,
    "representative_image_url": None,
}

DUMMY_WEEK = {
    "week_label": "Tuần 1 · 27/10 – 02/11/2026",
    "week_start": "2026-10-27",
    "week_end": "2026-11-02",
    "days_logged": 3,
    "total_kcal": 5400.0,
    "avg_daily_kcal": 1800.0,
    "days": [
        {**DUMMY_DAY_CELL, "day_label": "T2"},
        {**DUMMY_DAY_CELL_EMPTY, "day_label": "T3"},
        {**DUMMY_DAY_CELL, "day_label": "T4"},
        {**DUMMY_DAY_CELL_EMPTY, "day_label": "T5"},
        {**DUMMY_DAY_CELL_EMPTY, "day_label": "T6"},
        {**DUMMY_DAY_CELL_EMPTY, "day_label": "T7"},
        {**DUMMY_DAY_CELL_EMPTY, "day_label": "CN"},
    ],
}

WEEKLY_RESPONSE = {
    "user_id": 1,
    "weeks": 1,
    "streak_days": 3,
    "total_meals_logged": 42,
    "avg_daily_kcal": 1800.0,
    "avg_daily_protein_g": 120.0,
    "avg_daily_fat_g": 55.0,
    "avg_daily_carb_g": 210.0,
    "data": [DUMMY_WEEK],
}

DUMMY_MONTH = {
    "month_label": "tháng 10 2026",
    "month_start": "2026-10-01",
    "days_in_month": 31,
    "days_logged": 14,
    "total_kcal": 25200.0,
    "avg_daily_kcal": 1800.0,
    "days": [DUMMY_DAY_CELL] * 14 + [DUMMY_DAY_CELL_EMPTY] * 17,
}

MONTHLY_RESPONSE = {
    "user_id": 1,
    "months": 1,
    "streak_days": 3,
    "total_meals_logged": 42,
    "avg_daily_kcal": 1800.0,
    "avg_daily_protein_g": 120.0,
    "avg_daily_fat_g": 55.0,
    "avg_daily_carb_g": 210.0,
    "data": [DUMMY_MONTH],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_diary_repo():
    repo = MagicMock()
    app.dependency_overrides[get_diary_repo] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_diary_repo, None)


# ---------------------------------------------------------------------------
# Weekly diary tests
# ---------------------------------------------------------------------------


def test_weekly_diary_ok(client, mock_diary_repo):
    mock_diary_repo.weekly_diary.return_value = WEEKLY_RESPONSE
    resp = client.get("/api/v1/diary/weekly?weeks=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["weeks"] == 1
    assert body["streak_days"] == 3
    assert body["total_meals_logged"] == 42
    assert len(body["data"]) == 1
    week = body["data"][0]
    assert len(week["days"]) == 7
    # Check day labels
    labels = [d["day_label"] for d in week["days"]]
    assert labels == ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def test_weekly_diary_has_image_url(client, mock_diary_repo):
    mock_diary_repo.weekly_diary.return_value = WEEKLY_RESPONSE
    resp = client.get("/api/v1/diary/weekly?weeks=1")
    days = resp.json()["data"][0]["days"]
    # First day has image
    assert days[0]["representative_image_url"] is not None
    assert days[0]["has_meals"] is True
    # Second day is empty
    assert days[1]["representative_image_url"] is None
    assert days[1]["has_meals"] is False


def test_weekly_diary_default_weeks(client, mock_diary_repo):
    mock_diary_repo.weekly_diary.return_value = {**WEEKLY_RESPONSE, "weeks": 4}
    resp = client.get("/api/v1/diary/weekly")
    assert resp.status_code == 200
    mock_diary_repo.weekly_diary.assert_called_once()
    call_kwargs = mock_diary_repo.weekly_diary.call_args.kwargs
    assert call_kwargs["weeks"] == 4


def test_weekly_diary_invalid_weeks_zero(client, mock_diary_repo):
    resp = client.get("/api/v1/diary/weekly?weeks=0")
    assert resp.status_code == 422


def test_weekly_diary_max_weeks(client, mock_diary_repo):
    resp = client.get("/api/v1/diary/weekly?weeks=53")
    assert resp.status_code == 422


def test_weekly_diary_summary_fields(client, mock_diary_repo):
    mock_diary_repo.weekly_diary.return_value = WEEKLY_RESPONSE
    resp = client.get("/api/v1/diary/weekly?weeks=1")
    body = resp.json()
    assert "avg_daily_protein_g" in body
    assert "avg_daily_fat_g" in body
    assert "avg_daily_carb_g" in body
    assert body["avg_daily_protein_g"] == 120.0


def test_weekly_diary_unauthorized(client):
    app.dependency_overrides.clear()
    resp = client.get("/api/v1/diary/weekly")
    assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# Monthly diary tests
# ---------------------------------------------------------------------------


def test_monthly_diary_ok(client, mock_diary_repo):
    mock_diary_repo.monthly_diary.return_value = MONTHLY_RESPONSE
    resp = client.get("/api/v1/diary/monthly?months=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["months"] == 1
    assert body["streak_days"] == 3
    month = body["data"][0]
    assert month["month_label"] == "tháng 10 2026"
    assert month["days_in_month"] == 31
    assert len(month["days"]) == 31


def test_monthly_diary_image_cells(client, mock_diary_repo):
    mock_diary_repo.monthly_diary.return_value = MONTHLY_RESPONSE
    resp = client.get("/api/v1/diary/monthly?months=1")
    days = resp.json()["data"][0]["days"]
    # First 14 days have meals
    assert days[0]["has_meals"] is True
    assert days[0]["representative_image_url"] is not None
    # Rest are empty
    assert days[14]["has_meals"] is False
    assert days[14]["representative_image_url"] is None


def test_monthly_diary_avg_kcal_header(client, mock_diary_repo):
    mock_diary_repo.monthly_diary.return_value = MONTHLY_RESPONSE
    resp = client.get("/api/v1/diary/monthly?months=1")
    month = resp.json()["data"][0]
    # avg_daily_kcal used for the header "1.840 kcal/ngày"
    assert month["avg_daily_kcal"] == 1800.0


def test_monthly_diary_default_months(client, mock_diary_repo):
    mock_diary_repo.monthly_diary.return_value = {**MONTHLY_RESPONSE, "months": 2}
    resp = client.get("/api/v1/diary/monthly")
    assert resp.status_code == 200
    call_kwargs = mock_diary_repo.monthly_diary.call_args.kwargs
    assert call_kwargs["months"] == 2


def test_monthly_diary_invalid_months_zero(client, mock_diary_repo):
    resp = client.get("/api/v1/diary/monthly?months=0")
    assert resp.status_code == 422


def test_monthly_diary_max_months(client, mock_diary_repo):
    resp = client.get("/api/v1/diary/monthly?months=25")
    assert resp.status_code == 422


def test_monthly_diary_locket_calo_field(client, mock_diary_repo):
    mock_diary_repo.monthly_diary.return_value = MONTHLY_RESPONSE
    resp = client.get("/api/v1/diary/monthly?months=1")
    body = resp.json()
    # "Locket Calo" badge = total_meals_logged
    assert body["total_meals_logged"] == 42

