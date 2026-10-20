from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.database import PostgresDatabase


class UserNotFoundError(LookupError):
    pass


class DishNotFoundError(LookupError):
    pass


class NutritionTrackingRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    def update_metabolism_profile(
        self,
        *,
        user_id: int,
        gender: str,
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
                SET gender = %s,
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
                    gender,
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
        total_calories: float,
        image_url: str | None,
        consumed_at: datetime,
    ) -> dict[str, Any]:
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            dish_name: str | None = None
            if dish_id is not None:
                cursor.execute("SELECT dishes_name FROM dishes WHERE id = %s", (dish_id,))
                dish = cursor.fetchone()
                if dish is None:
                    raise DishNotFoundError(f"Dish {dish_id} does not exist")
                dish_name = str(dish["dishes_name"])

            cursor.execute(
                """
                INSERT INTO meal_logs (
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    total_calories,
                    image_url,
                    consumed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    total_calories,
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
                    total_calories,
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
