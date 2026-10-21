from __future__ import annotations

import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from calcucalo.api.app import app
from calcucalo.api.auth import get_auth_service

BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    service = get_auth_service()
    client = TestClient(app)
    email = f"nutrition-meals-{uuid.uuid4().hex}@example.invalid"
    password = secrets.token_urlsafe(24)

    with service.database.connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT d.id, SUM(i.calories * di.quantity / 100.0) AS catalog_calories
            FROM dishes AS d
            JOIN dish_ingredients AS di ON di.dish_id = d.id
            JOIN ingredients AS i ON i.id = di.ingredient_id
            GROUP BY d.id
            HAVING SUM(i.calories * di.quantity / 100.0) IS NOT NULL
            ORDER BY d.id
            LIMIT 1
            """
        )
        dish = cursor.fetchone()
    assert dish is not None, "At least one dish must have ingredient nutrition data"
    dish_id = int(dish[0])
    expected_meal_calories = round(float(dish[1]), 1)

    try:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Nutrition API smoke"},
        )
        assert registered.status_code == 201, registered.text
        access_token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        calculated = client.post(
            "/api/v1/nutrition/calculate",
            headers=headers,
            json={
                "sex_for_equation": "male",
                "age": 30,
                "height_cm": 175,
                "weight_kg": 70,
                "activity_level": "moderate",
                "goal": "maintain_weight",
            },
        )
        assert calculated.status_code == 200, calculated.text
        assert calculated.json()["target_kcal_per_day"] == 2556.0

        now = datetime.now(BANGKOK_TIMEZONE)
        created = client.post(
            "/api/v1/meals",
            headers=headers,
            json={
                "dish_id": dish_id,
                "meal_type": "lunch",
                "quantity": 1,
                "consumed_at": now.isoformat(),
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["calorie_source"] == "dish_catalog"
        assert created.json()["total_calories"] == expected_meal_calories

        daily = client.get(
            "/api/v1/meals/daily",
            headers=headers,
            params={"date": now.date().isoformat()},
        )
        assert daily.status_code == 200, daily.text
        payload = daily.json()
        assert payload["meal_count"] == 1, payload
        assert payload["total_calories"] == expected_meal_calories, payload
        assert payload["remaining_kcal"] == round(2556.0 - expected_meal_calories, 1), payload
        assert payload["calorie_source_counts"]["dish_catalog"] == 1, payload
        print("Nutrition calculation and meal log smoke test passed.")
        return 0
    finally:
        with service.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE email = %s", (email,))


if __name__ == "__main__":
    raise SystemExit(main())
