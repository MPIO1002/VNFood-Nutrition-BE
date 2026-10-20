from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi.testclient import TestClient

from calcucalo.api.app import app
from calcucalo.api.auth import get_current_user
from calcucalo.api.nutrition_meals import get_nutrition_tracking_repository


class FakeNutritionTrackingRepository:
    def __init__(self) -> None:
        self.profile_update: dict[str, Any] | None = None
        self.meal = {
            "id": 10,
            "user_id": 7,
            "dish_id": 1,
            "dish_name": "Cơm tấm",
            "meal_type": "lunch",
            "quantity": 1.0,
            "total_calories": 620.0,
            "image_url": None,
            "consumed_at": datetime(2026, 10, 21, 12, 30),
            "created_at": datetime(2026, 10, 21, 12, 31),
            "updated_at": datetime(2026, 10, 21, 12, 31),
        }

    def update_metabolism_profile(self, **values: Any) -> None:
        self.profile_update = values

    def create_meal_log(self, **values: Any) -> dict[str, Any]:
        return {**self.meal, **values, "id": 10, "dish_name": "Cơm tấm"}

    def daily_meals(
        self, *, user_id: int, day: date
    ) -> tuple[list[dict[str, Any]], float | None]:
        assert user_id == 7
        assert day == date(2026, 10, 21)
        return [self.meal], 2555.6


def _client_with_overrides(
    repository: FakeNutritionTrackingRepository,
) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {
        "id": 7,
        "email": "user@example.com",
    }
    app.dependency_overrides[get_nutrition_tracking_repository] = lambda: repository
    return TestClient(app)


def test_calculate_nutrition_persists_profile_and_returns_target() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/nutrition/calculate",
            json={
                "gender": "male",
                "age": 30,
                "height_cm": 175,
                "weight_kg": 70,
                "activity_level": "moderate",
                "goal": "maintain_weight",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == 7
    assert payload["bmi"] == 22.9
    assert payload["bmr_kcal_per_day"] == 1648.8
    assert payload["target_kcal_per_day"] == 2555.6
    assert repository.profile_update is not None
    assert repository.profile_update["target_calories"] == 2555.6


def test_create_meal_and_get_daily_summary() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        created = client.post(
            "/api/v1/meals",
            json={
                "dish_id": 1,
                "meal_type": "lunch",
                "quantity": 1,
                "total_calories": 620,
                "consumed_at": "2026-10-21T12:30:00+07:00",
            },
        )
        daily = client.get("/api/v1/meals/daily", params={"date": "2026-10-21"})
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert created.json()["dish_name"] == "Cơm tấm"
    assert daily.status_code == 200
    payload = daily.json()
    assert payload["meal_count"] == 1
    assert payload["total_calories"] == 620.0
    assert payload["target_kcal_per_day"] == 2555.6
    assert payload["remaining_kcal"] == 1935.6


def test_metabolism_request_validation_rejects_minor_age() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/nutrition/calculate",
            json={
                "gender": "male",
                "age": 15,
                "height_cm": 170,
                "weight_kg": 60,
                "activity_level": "moderate",
                "goal": "maintain_weight",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_nutrition_and_meal_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert {
        "/api/v1/nutrition/calculate",
        "/api/v1/meals",
        "/api/v1/meals/daily",
    } <= paths
