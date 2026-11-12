import threading
from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.database import PostgresDatabase
from ..domain.dish_nutrition import (
    PortionOutOfRangeError,
    compute_dish_nutrition,
    quantity_for_portion,
)

MAX_MEAL_CALORIES_KCAL = 20_000.0


class UserNotFoundError(LookupError):
    pass


class DishNotFoundError(LookupError):
    pass


class DishNutritionUnavailableError(LookupError):
    pass


class MealCalorieLimitError(ValueError):
    pass


class InvalidPortionError(ValueError):
    pass


class NutritionTrackingRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def initialize_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self.database.connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    ALTER TABLE meal_logs
                        ADD COLUMN IF NOT EXISTS protein_g DOUBLE PRECISION,
                        ADD COLUMN IF NOT EXISTS fat_g DOUBLE PRECISION,
                        ADD COLUMN IF NOT EXISTS carb_g DOUBLE PRECISION,
                        ADD COLUMN IF NOT EXISTS estimated_portion_g DOUBLE PRECISION,
                        ADD COLUMN IF NOT EXISTS base_portion_g DOUBLE PRECISION;
                    """
                )
            self._schema_ready = True

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
        protein_g: float | None = None,
        fat_g: float | None = None,
        carb_g: float | None = None,
        estimated_portion_g: float | None = None,
        image_url: str | None,
        consumed_at: datetime,
    ) -> dict[str, Any]:
        self.initialize_schema()
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            dish_name: str | None = None
            catalog_base_portion_g: float | None = None
            catalog_nutrition: dict[str, Any] | None = None
            components: list[dict[str, Any]] = []
            if dish_id is not None:
                cursor.execute(
                    '''
                    SELECT
                        d.dishes_name,
                        di.ingredient_id,
                        i.ingredients_name,
                        di.quantity AS default_g,
                        i.calories   AS cal_per_100g,
                        i.protein    AS protein,
                        i.fat        AS fat,
                        i.carb       AS carb
                    FROM dishes AS d
                    LEFT JOIN dish_ingredients AS di ON di.dish_id = d.id
                    LEFT JOIN ingredients AS i ON i.id = di.ingredient_id
                    WHERE d.id = %s
                    ''',
                    (dish_id,),
                )
                rows = cursor.fetchall()
                if not rows:
                    raise DishNotFoundError(f"Dish {dish_id} does not exist")
                dish_name = str(rows[0]["dishes_name"])
                components = [
                    {
                        "ingredient_id": str(row["ingredient_id"]),
                        "name": str(row["ingredients_name"]),
                        "default_g": float(row["default_g"]),
                        "cal_per_100g": float(row["cal_per_100g"]),
                        "protein": float(row["protein"]),
                        "fat": float(row["fat"]),
                        "carb": float(row["carb"]),
                    }
                    for row in rows
                    if row["ingredient_id"] is not None and row["default_g"] is not None
                ]
                if components:
                    base_total = sum(float(item["default_g"]) for item in components)
                    if base_total > 0:
                        catalog_base_portion_g = base_total
                        catalog_nutrition = compute_dish_nutrition(
                            components,
                            portion_g=catalog_base_portion_g,
                            base_portion_g=catalog_base_portion_g,
                        )

            # A physical portion from /food/analyze wins over the client quantity:
            # the server owns the conversion so analyze and save cannot disagree.
            portion_g: float | None = None
            if estimated_portion_g is not None:
                if catalog_base_portion_g is None:
                    raise DishNutritionUnavailableError(
                        f"Dish {dish_id} has no ingredient nutrition data; "
                        "estimated_portion_g cannot be converted to a serving count"
                    )
                try:
                    quantity = quantity_for_portion(estimated_portion_g, catalog_base_portion_g)
                except PortionOutOfRangeError as exc:
                    raise InvalidPortionError(str(exc)) from exc
                portion_g = max(float(estimated_portion_g), 1.0)
            elif catalog_base_portion_g is not None:
                portion_g = quantity * catalog_base_portion_g

            portion_nutrition = (
                compute_dish_nutrition(
                    components,
                    portion_g=portion_g,
                    base_portion_g=catalog_base_portion_g,
                )
                if catalog_base_portion_g is not None
                else None
            )
            totals = portion_nutrition["estimated_totals"] if portion_nutrition else None

            if total_calories is None:
                if totals is None:
                    raise DishNutritionUnavailableError(
                        f"Dish {dish_id} has no ingredient nutrition data; "
                        "provide total_calories manually"
                    )
                resolved_total_calories = totals["calories_kcal"]
                if resolved_total_calories > MAX_MEAL_CALORIES_KCAL:
                    raise MealCalorieLimitError(
                        f"Calculated meal calories must not exceed {MAX_MEAL_CALORIES_KCAL:.0f}"
                    )
                calorie_source = "dish_catalog"
            else:
                resolved_total_calories = total_calories
                calorie_source = "manual"

            resolved_protein_g = protein_g if protein_g is not None else (totals["protein_g"] if totals else None)
            resolved_fat_g = fat_g if fat_g is not None else (totals["fat_g"] if totals else None)
            resolved_carb_g = carb_g if carb_g is not None else (totals["carb_g"] if totals else None)

            catalog_calories_per_serving = (
                catalog_nutrition["estimated_totals"]["calories_kcal"]
                if catalog_nutrition is not None
                else None
            )

            cursor.execute(
                '''
                INSERT INTO meal_logs (
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    total_calories,
                    protein_g,
                    fat_g,
                    carb_g,
                    calorie_source,
                    catalog_calories_per_serving,
                    estimated_portion_g,
                    base_portion_g,
                    image_url,
                    consumed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    total_calories,
                    protein_g,
                    fat_g,
                    carb_g,
                    calorie_source,
                    catalog_calories_per_serving,
                    estimated_portion_g,
                    base_portion_g,
                    image_url,
                    consumed_at,
                    created_at,
                    updated_at
                ''',
                (
                    user_id,
                    dish_id,
                    meal_type,
                    quantity,
                    resolved_total_calories,
                    resolved_protein_g,
                    resolved_fat_g,
                    resolved_carb_g,
                    calorie_source,
                    catalog_calories_per_serving,
                    portion_g if estimated_portion_g is not None else None,
                    catalog_base_portion_g,
                    image_url,
                    consumed_at,
                ),
            )
            meal = dict(cursor.fetchone())
            meal["dish_name"] = dish_name
            return meal

    def daily_meals(
        self, *, user_id: int, day: date
    ) -> tuple[list[dict[str, Any]], float | None, str | None]:
        self.initialize_schema()
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            cursor.execute(
                """
                SELECT target_calories, goal
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
                    ml.protein_g,
                    ml.fat_g,
                    ml.carb_g,
                    ml.calorie_source,
                    ml.catalog_calories_per_serving,
                    ml.estimated_portion_g,
                    ml.base_portion_g,
                    ml.image_url,
                    ml.consumed_at,
                    ml.created_at,
                    ml.updated_at
                FROM meal_logs AS ml
                LEFT JOIN dishes AS d ON d.id = ml.dish_id
                WHERE ml.user_id = %s
                  AND ml.consumed_at >= %s
                  AND ml.consumed_at < %s
                ORDER BY
                    CASE LOWER(BTRIM(ml.meal_type))
                        WHEN 'breakfast' THEN 1
                        WHEN 'lunch' THEN 2
                        WHEN 'snack' THEN 3
                        WHEN 'dinner' THEN 4
                        ELSE 0
                    END DESC,
                    ml.consumed_at ASC,
                    ml.id ASC
                """,
                (user_id, start, end),
            )
            meals = [dict(row) for row in cursor.fetchall()]
            target = user["target_calories"]
            return meals, (float(target) if target is not None else None), user.get("goal")


def _dict_cursor(connection: Any) -> Any:
    from psycopg2.extras import RealDictCursor

    return connection.cursor(cursor_factory=RealDictCursor)
