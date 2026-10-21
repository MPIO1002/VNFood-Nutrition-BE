from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.database import PostgresDatabase

MAX_MEAL_CALORIES_KCAL = 20_000.0


class UserNotFoundError(LookupError):
    pass


class DishNotFoundError(LookupError):
    pass


class DishNutritionUnavailableError(LookupError):
    pass


class MealCalorieLimitError(ValueError):
    pass


class NutritionTrackingRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def update_metabolism_profile(
        self,
        *,
        user_id: int,
        sex_for_equation: str,
        age: int,
        height_cm: float,
        weight_kg: float,
        activity_level: str,
        goal: str,
        bmi: float,
        tdee: float,
        target_calories: float,
    ) -> None:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET sex_for_equation = %s,
                    gender = %s,
                    age = %s,
                    height = %s,
                    weight = %s,
                    activity_level = %s,
                    goal = %s,
                    bmi = %s,
                    tdee = %s,
                    target_calories = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    sex_for_equation,
                    sex_for_equation,
                    age,
                    height_cm,
                    weight_kg,
                    activity_level,
                    goal,
                    bmi,
                    tdee,
                    target_calories,
                    user_id,
                ),
            )
            if cursor.rowcount != 1:
                raise UserNotFoundError(f"User {user_id} does not exist")

    def create_meal_log(
        self,
        *,
        user_id: int,
        dish_id: int | None,
        meal_type: str,
        quantity: float,
        total_calories: float | None,
        image_url: str | None,
        consumed_at: datetime,
    ) -> dict[str, Any]:
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            dish_name: str | None = None
            catalog_calories_per_serving: float | None = None
            if dish_id is not None:
                cursor.execute(
                    """
                    SELECT
                        d.dishes_name,
                        SUM(i.calories * di.quantity / 100.0) AS catalog_calories_per_serving
                    FROM dishes AS d
                    LEFT JOIN dish_ingredients AS di ON di.dish_id = d.id
                    LEFT JOIN ingredients AS i ON i.id = di.ingredient_id
                    WHERE d.id = %s
                    GROUP BY d.id, d.dishes_name
                    """,
                    (dish_id,),
                )
                dish = cursor.fetchone()
                if dish is None:
                    raise DishNotFoundError(f"Dish {dish_id} does not exist")
                dish_name = str(dish["dishes_name"])
                catalog_value = dish["catalog_calories_per_serving"]
                if catalog_value is not None:
                    catalog_calories_per_serving = round(float(catalog_value), 1)

            if total_calories is None:
                if catalog_calories_per_serving is None:
                    raise DishNutritionUnavailableError(
                        f"Dish {dish_id} has no ingredient nutrition data; "
                        "provide total_calories manually"
                    )
                resolved_total_calories = round(catalog_calories_per_serving * quantity, 1)
                if resolved_total_calories > MAX_MEAL_CALORIES_KCAL:
                    raise MealCalorieLimitError(
                        f"Calculated meal calories must not exceed {MAX_MEAL_CALORIES_KCAL:.0f}"
                    )
                calorie_source = "dish_catalog"
            else:
                resolved_total_calories = total_calories
                calorie_source = "manual"

            cursor.execute(
                """
                INSERT INTO meal_logs (
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    total_calories,
                    calorie_source,
                    catalog_calories_per_serving,
                    image_url,
                    consumed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    total_calories,
                    calorie_source,
                    catalog_calories_per_serving,
                    image_url,
                    consumed_at,
                    created_at,
                    updated_at
                """,
                (
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    resolved_total_calories,
                    calorie_source,
                    catalog_calories_per_serving,
                    image_url,
                    consumed_at,
                ),
            )
            meal = dict(cursor.fetchone())
            meal["dish_name"] = dish_name
            return meal

    def daily_meals(self, *, user_id: int, day: date) -> tuple[list[dict[str, Any]], float | None]:
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            cursor.execute(
                """
                SELECT target_calories
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            user = cursor.fetchone()
            if user is None:
                raise UserNotFoundError(f"User {user_id} does not exist")

            cursor.execute(
                """
                SELECT
                    ml.id,
                    ml.user_id,
                    ml.dish_id,
                    d.dishes_name AS dish_name,
                    ml.meal_type,
                    ml.quantity,
                    ml.total_calories,
                    ml.calorie_source,
                    ml.catalog_calories_per_serving,
                    ml.image_url,
                    ml.consumed_at,
                    ml.created_at,
                    ml.updated_at
                FROM meal_logs AS ml
                LEFT JOIN dishes AS d ON d.id = ml.dish_id
                WHERE ml.user_id = %s
                  AND ml.consumed_at >= %s
                  AND ml.consumed_at < %s
                ORDER BY ml.consumed_at ASC, ml.id ASC
                """,
                (user_id, start, end),
            )
            meals = [dict(row) for row in cursor.fetchall()]
            target = user["target_calories"]
            return meals, float(target) if target is not None else None


def _dict_cursor(connection: Any) -> Any:
    from psycopg2.extras import RealDictCursor

    return connection.cursor(cursor_factory=RealDictCursor)
