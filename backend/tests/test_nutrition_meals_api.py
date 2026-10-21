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
            "calorie_source": "manual",
            "catalog_calories_per_serving": None,
            "image_url": None,
            "consumed_at": datetime(2026, 10, 21, 12, 30),
            "created_at": datetime(2026, 10, 21, 12, 31),
            "updated_at": datetime(2026, 10, 21, 12, 31),
        }

    def update_metabolism_profile(self, **values: Any) -> None:
        self.profile_update = values

    def create_meal_log(self, **values: Any) -> dict[str, Any]:
        if values["total_calories"] is None:
            total_calories = round(620.0 * values["quantity"], 1)
            calorie_source = "dish_catalog"
            catalog_calories = 620.0
        else:
            total_calories = values["total_calories"]
            calorie_source = "manual"
            catalog_calories = None
        return {
            **self.meal,
            **values,
            "id": 10,
            "dish_name": "Cơm tấm",
            "total_calories": total_calories,
            "calorie_source": calorie_source,
            "catalog_calories_per_serving": catalog_calories,
        }

    def daily_meals(self, *, user_id: int, day: date) -> tuple[list[dict[str, Any]], float | None]:
        assert user_id == 7
        assert day == date(2026, 10, 21)
        return [self.meal], 2556.0


def _client_with_overrides(
    repository: FakeNutritionTrackingRepository,
) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {
        "id": 7,
        "email": "user@example.com",
    }
    app.dependency_overrides[get_nutrition_tracking_repository] = lambda: repository
    return TestClient(app)


def test_calculate_nutrition_persists_profile_and_returns_safer_contract() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/nutrition/calculate",
            json={
                "sex_for_equation": "male",
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
    assert payload["bmi_category_general"] == "healthy_weight"
    assert payload["bmi_category_asian"] == "healthy_weight"
    assert payload["estimated_rmr_kcal_per_day"] == 1649.0
    assert payload["target_kcal_per_day"] == 2556.0
    assert payload["is_estimate"] is True
    assert payload["warnings"]
    assert repository.profile_update is not None
    assert repository.profile_update["sex_for_equation"] == "male"
    assert repository.profile_update["target_calories"] == 2556.0


def test_legacy_gender_input_alias_remains_supported() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/nutrition/calculate",
            json={
                "gender": "female",
                "age": 28,
                "height_cm": 160,
                "weight_kg": 60,
                "activity_level": "light",
                "goal": "gain_weight",
                "goal_pace": "gradual",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["sex_for_equation"] == "female"


def test_unsafe_weight_loss_returns_422_instead_of_calorie_target() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/nutrition/calculate",
            json={
                "sex_for_equation": "female",
                "age": 30,
                "height_cm": 170,
                "weight_kg": 50,
                "activity_level": "sedentary",
                "goal": "lose_weight",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_nutrition_target"
    assert repository.profile_update is None


def test_create_manual_meal_and_get_daily_summary() -> None:
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
    assert created.json()["calorie_source"] == "manual"
    assert daily.status_code == 200
    payload = daily.json()
    assert payload["meal_count"] == 1
    assert payload["total_calories"] == 620.0
    assert payload["target_kcal_per_day"] == 2556.0
    assert payload["remaining_kcal"] == 1936.0
    assert payload["calorie_source_counts"] == {"dish_catalog": 0, "manual": 1}


def test_create_meal_can_calculate_calories_from_dish_catalog() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/meals",
            json={"dish_id": 1, "meal_type": "dinner", "quantity": 1.5},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["total_calories"] == 930.0
    assert response.json()["calorie_source"] == "dish_catalog"
    assert response.json()["catalog_calories_per_serving"] == 620.0


def test_meal_requires_dish_or_manual_calories() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/meals",
            json={"meal_type": "snack", "quantity": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_metabolism_request_validation_rejects_minor_age() -> None:
    repository = FakeNutritionTrackingRepository()
    client = _client_with_overrides(repository)
    try:
        response = client.post(
            "/api/v1/nutrition/calculate",
            json={
                "sex_for_equation": "male",
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
