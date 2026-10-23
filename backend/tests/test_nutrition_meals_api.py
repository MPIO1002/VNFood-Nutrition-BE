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
        self.profile: dict[str, Any] = {
            "id": 7,
            "email": "user@example.com",
            "full_name": "Test User",
            "gender": "male",
            "sex_for_equation": "male",
            "age": 30,
            "height": 175.0,
            "weight": 70.0,
            "activity_level": "moderate",
            "goal": "maintain_weight",
            "bmi": 22.9,
            "tdee": 2556.0,
            "target_calories": 2556.0,
            "is_active": True,
            "created_at": datetime(2026, 10, 21, 12, 0),
            "updated_at": datetime(2026, 10, 21, 12, 0),
        }
        self.meal = {
            "id": 10,
            "user_id": 7,
            "dish_id": 1,
            "dish_name": "Cơm tấm",
            "meal_type": "lunch",
            "quantity": 1.0,
            "total_calories": 620.0,
            "protein_g": 25.0,
            "fat_g": 15.0,
            "carb_g": 85.0,
            "calorie_source": "manual",
            "catalog_calories_per_serving": None,
            "image_url": None,
            "consumed_at": datetime(2026, 10, 21, 12, 30),
            "created_at": datetime(2026, 10, 21, 12, 31),
            "updated_at": datetime(2026, 10, 21, 12, 31),
        }

    def update_metabolism_profile(self, **values: Any) -> None:
        self.profile_update = values
        self.profile.update(values)

    def create_meal_log(self, **values: Any) -> dict[str, Any]:
        if values["total_calories"] is None:
            total_calories = round(620.0 * values["quantity"], 1)
            calorie_source = "dish_catalog"
            catalog_calories = 620.0
            protein_g = round(25.0 * values["quantity"], 1)
            fat_g = round(15.0 * values["quantity"], 1)
            carb_g = round(85.0 * values["quantity"], 1)
        else:
            total_calories = values["total_calories"]
            calorie_source = "manual"
            catalog_calories = None
            protein_g = values["protein_g"] if values.get("protein_g") is not None else 25.0
            fat_g = values["fat_g"] if values.get("fat_g") is not None else 15.0
            carb_g = values["carb_g"] if values.get("carb_g") is not None else 85.0
        return {
            **self.meal,
            **values,
            "id": 10,
            "dish_name": "Cơm tấm",
            "total_calories": total_calories,
            "protein_g": protein_g,
            "fat_g": fat_g,
            "carb_g": carb_g,
            "calorie_source": calorie_source,
            "catalog_calories_per_serving": catalog_calories,
        }

    def daily_meals(
        self, *, user_id: int, day: date
    ) -> tuple[list[dict[str, Any]], float | None, str | None]:
        assert user_id == 7
        assert day == date(2026, 10, 21)
        return [self.meal], 2556.0, "maintain_weight"


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
    assert payload["target_kcal_per_day"] == 2556.0
    assert payload["target_protein_g"] == 159.8
    assert payload["target_carb_g"] == 319.5
    assert payload["target_fat_g"] == 71.0
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


def test_calculate_with_weight_change_and_timeline() -> None:
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
                "goal": "lose_weight",
                "goal_pace": "standard",
                "weight_change_kg": 4.0,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["current_weight_kg"] == 70.0
    assert data["weight_change_kg"] == 4.0
    assert data["target_weight_kg"] == 66.0
    assert data["daily_calorie_adjustment"] == -500.0
    assert data["weekly_pace_kg"] == 0.5
    # 4 * 7700 / 500 = 61.6 -> 62 days
    assert data["estimated_days"] == 62
    assert data["estimated_weeks"] == 8.9
    assert data["target_date"] is not None
    assert "summary_message" in data


def test_maintain_weight_rejects_nonzero_weight_change() -> None:
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
                "weight_change_kg": 3.0,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


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
    assert created.json()["protein_g"] == 25.0
    assert daily.status_code == 200
    payload = daily.json()
    assert payload["meal_count"] == 1
    assert payload["total_calories"] == 620.0
    assert payload["target_kcal_per_day"] == 2556.0
    assert payload["remaining_kcal"] == 1936.0
    assert payload["total_protein_g"] == 25.0
    assert payload["target_protein_g"] == 159.8
    assert payload["remaining_protein_g"] == 134.8
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
    assert response.json()["protein_g"] == 37.5


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
