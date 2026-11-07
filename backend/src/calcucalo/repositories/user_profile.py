"""Repository: user profile CRUD and progress / weight-log queries.

Tables used:
    users           – profile fields (weight, height, bmi, target_calories …)
    weight_history  – history of weight updates (created by migration 0007)
    meal_logs       – daily intake aggregates for progress stats
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.database import PostgresDatabase
from ..services.metabolism import (
    UnsafeCalorieTargetError,
    UnsupportedMetabolismProfileError,
    calculate_metabolism,
)

_logger = logging.getLogger(__name__)

_WEIGHT_SCHEMA = """
-- Adapt existing weight_history table: add note column if missing
ALTER TABLE weight_history
    ADD COLUMN IF NOT EXISTS note TEXT;

-- Add avatar_url to users if not present
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- Add special-condition flags (migration 0008)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pregnant_or_breastfeeding    BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS competitive_athlete           BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS metabolism_affecting_condition BOOLEAN NOT NULL DEFAULT FALSE;

-- Ensure indexes
CREATE INDEX IF NOT EXISTS idx_weight_history_user_id
    ON weight_history(user_id);

CREATE INDEX IF NOT EXISTS idx_weight_history_recorded_at
    ON weight_history(user_id, recorded_at DESC);
"""


class UserNotFoundError(LookupError):
    pass


class UserProfileRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def initialize_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self.database.connection() as conn, conn.cursor() as cur:
                cur.execute(_WEIGHT_SCHEMA)
            self._schema_ready = True

    # ------------------------------------------------------------------
    # Profile read
    # ------------------------------------------------------------------

    def get_profile(self, user_id: int) -> dict[str, Any]:
        """Return full user profile row."""
        self.initialize_schema()
        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    email,
                    full_name,
                    avatar_url,
                    gender,
                    sex_for_equation,
                    age,
                    height,
                    weight,
                    activity_level,
                    goal,
                    bmi,
                    tdee,
                    target_calories,
                    COALESCE(pregnant_or_breastfeeding, FALSE)     AS pregnant_or_breastfeeding,
                    COALESCE(competitive_athlete, FALSE)           AS competitive_athlete,
                    COALESCE(metabolism_affecting_condition, FALSE) AS metabolism_affecting_condition,
                    is_active,
                    created_at,
                    updated_at
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise UserNotFoundError(f"User {user_id} does not exist")
        return dict(row)

    # ------------------------------------------------------------------
    # Profile update – expanded
    # ------------------------------------------------------------------

    def update_profile(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        avatar_url: str | None = None,
        weight_kg: float | None = None,
        height_cm: float | None = None,
        age: int | None = None,
        goal: str | None = None,
        activity_level: str | None = None,
        pregnant_or_breastfeeding: bool | None = None,
        competitive_athlete: bool | None = None,
        metabolism_affecting_condition: bool | None = None,
    ) -> dict[str, Any]:
        """Update user profile fields.

        Rules:
        - All parameters are optional; omitting one leaves the DB column unchanged.
        - If weight_kg is supplied it is also written to weight_history.
        - After saving, when the user has all required fields for Mifflin-St Jeor
          (weight, height, age, goal, activity_level, sex_for_equation) AND no
          special-condition flag is True, BMI / TDEE / target_calories are
          recalculated and written back automatically.
        """
        self.initialize_schema()

        # ------------------------------------------------------------------ #
        # 1. Build UPDATE for users table                                     #
        # ------------------------------------------------------------------ #
        fields: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
        values: list[Any] = []

        if full_name is not None:
            fields.append("full_name = %s")
            values.append(full_name)
        if avatar_url is not None:
            fields.append("avatar_url = %s")
            values.append(avatar_url)
        if weight_kg is not None:
            fields.append("weight = %s")
            values.append(weight_kg)
        if height_cm is not None:
            fields.append("height = %s")
            values.append(height_cm)
        if age is not None:
            fields.append("age = %s")
            values.append(age)
        if goal is not None:
            fields.append("goal = %s")
            values.append(goal)
        if activity_level is not None:
            fields.append("activity_level = %s")
            values.append(activity_level)
        if pregnant_or_breastfeeding is not None:
            fields.append("pregnant_or_breastfeeding = %s")
            values.append(pregnant_or_breastfeeding)
        if competitive_athlete is not None:
            fields.append("competitive_athlete = %s")
            values.append(competitive_athlete)
        if metabolism_affecting_condition is not None:
            fields.append("metabolism_affecting_condition = %s")
            values.append(metabolism_affecting_condition)

        values.append(user_id)
        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"

        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            cur.execute(sql, values)
            if cur.rowcount != 1:
                raise UserNotFoundError(f"User {user_id} does not exist")

            # ---------------------------------------------------------------- #
            # 2. Write weight_history if weight changed                        #
            # ---------------------------------------------------------------- #
            if weight_kg is not None:
                cur.execute(
                    """
                    INSERT INTO weight_history (user_id, weight, recorded_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    """,
                    (user_id, weight_kg),
                )

            # ---------------------------------------------------------------- #
            # 3. Fetch full updated row for TDEE recalc decision               #
            # ---------------------------------------------------------------- #
            cur.execute(
                """
                SELECT weight, height, age, goal, activity_level, sex_for_equation,
                       COALESCE(pregnant_or_breastfeeding, FALSE)      AS pregnant_or_breastfeeding,
                       COALESCE(competitive_athlete, FALSE)            AS competitive_athlete,
                       COALESCE(metabolism_affecting_condition, FALSE)  AS metabolism_affecting_condition
                FROM users WHERE id = %s
                """,
                (user_id,),
            )
            u = dict(cur.fetchone())  # type: ignore[arg-type]

        # ------------------------------------------------------------------ #
        # 4. Recalculate BMI / TDEE / target_calories when possible          #
        # ------------------------------------------------------------------ #
        has_special_condition = (
            u["pregnant_or_breastfeeding"]
            or u["competitive_athlete"]
            or u["metabolism_affecting_condition"]
        )
        has_required = all([
            u["weight"], u["height"], u["age"],
            u["goal"], u["activity_level"], u["sex_for_equation"],
        ])

        if has_required and not has_special_condition:
            try:
                result = calculate_metabolism(
                    sex_for_equation=u["sex_for_equation"],
                    age=int(u["age"]),
                    height_cm=float(u["height"]),
                    weight_kg=float(u["weight"]),
                    activity_level=u["activity_level"],
                    goal=u["goal"],
                )
                with self.database.connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE users
                        SET bmi = %s, tdee = %s, target_calories = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (result.bmi, result.estimated_tdee_kcal_per_day,
                         result.target_kcal_per_day, user_id),
                    )
            except (UnsafeCalorieTargetError, UnsupportedMetabolismProfileError,
                    ValueError):
                # Data present but outside safe range — skip recalc silently
                _logger.debug(
                    "TDEE recalc skipped for user %s: profile outside supported range",
                    user_id,
                )

        return self.get_profile(user_id)

    # ------------------------------------------------------------------
    # Weight log – write
    # ------------------------------------------------------------------

    def add_weight_log(
        self,
        user_id: int,
        *,
        weight_kg: float,
        recorded_at: datetime | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new weight measurement into weight_history and update users.weight.

        Uses the existing weight_history table (legacy). Returns a normalised dict
        with key ``weight_kg`` mapped from the ``weight`` column.
        """
        self.initialize_schema()
        recorded_at = recorded_at or datetime.utcnow()
        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            # Insert into existing weight_history table
            cur.execute(
                """
                INSERT INTO weight_history (user_id, weight, recorded_at, note)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, weight, recorded_at, note
                """,
                (user_id, weight_kg, recorded_at, note),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to insert weight log")

            # Keep users.weight in sync
            cur.execute(
                """
                UPDATE users
                SET weight = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (weight_kg, user_id),
            )
            if cur.rowcount != 1:
                raise UserNotFoundError(f"User {user_id} does not exist")

        result = dict(row)
        # Normalise column name: weight → weight_kg for API consistency
        result["weight_kg"] = float(result.pop("weight"))
        return result

    # ------------------------------------------------------------------
    # Weight log – read history
    # ------------------------------------------------------------------

    def get_weight_history(
        self,
        user_id: int,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Return the most recent *limit* weight log entries (newest first).

        Reads from the existing weight_history table and normalises the
        ``weight`` column to ``weight_kg`` for API consistency.
        """
        self.initialize_schema()
        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT id, user_id, weight, recorded_at, note
                FROM weight_history
                WHERE user_id = %s
                ORDER BY recorded_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
        # Normalise: weight → weight_kg
        for row in rows:
            row["weight_kg"] = float(row.pop("weight"))
        return rows

    # ------------------------------------------------------------------
    # Progress stats – weekly
    # ------------------------------------------------------------------

    def weekly_stats(
        self,
        user_id: int,
        *,
        start: date,
        end: date,    # inclusive
    ) -> list[dict[str, Any]]:
        """Aggregate daily meal_logs into weekly buckets for [start, end].

        Weeks are Mon-Sun (ISO). Partial weeks at range boundaries are included.
        Each week shows totals even when days_logged == 0 (all zeros).

        Returns list of weekly summary dicts ordered oldest→newest.
        """
        self.initialize_schema()
        end_excl = end + timedelta(days=1)
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end_excl, time.min)

        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            cur.execute("SELECT target_calories FROM users WHERE id = %s", (user_id,))
            user_row = cur.fetchone()
            if user_row is None:
                raise UserNotFoundError(f"User {user_id} does not exist")
            target_kcal: float | None = (
                float(user_row["target_calories"]) if user_row["target_calories"] else None
            )

            cur.execute(
                """
                SELECT
                    DATE_TRUNC('week', consumed_at)::date  AS week_start,
                    COUNT(*)                               AS meal_count,
                    ROUND(SUM(total_calories)::numeric, 1) AS total_calories,
                    ROUND(SUM(COALESCE(protein_g, 0))::numeric, 1) AS total_protein_g,
                    ROUND(SUM(COALESCE(fat_g,     0))::numeric, 1) AS total_fat_g,
                    ROUND(SUM(COALESCE(carb_g,    0))::numeric, 1) AS total_carb_g,
                    COUNT(DISTINCT consumed_at::date)               AS days_logged
                FROM meal_logs
                WHERE user_id = %s
                  AND consumed_at >= %s
                  AND consumed_at <  %s
                GROUP BY week_start
                ORDER BY week_start
                """,
                (user_id, start_dt, end_dt),
            )
            rows = {r["week_start"]: dict(r) for r in cur.fetchall()}

        # Walk Mon-aligned weeks from start to end
        results: list[dict[str, Any]] = []
        week_monday = start - timedelta(days=start.weekday())
        cursor = week_monday
        while cursor <= end:
            w_start = cursor
            w_end = cursor + timedelta(days=6)
            effective_start = max(w_start, start)
            effective_end = min(w_end, end)
            match = rows.get(w_start)

            week_total_kcal = float(match["total_calories"]) if match else 0.0
            days = int(match["days_logged"]) if match else 0
            avg_daily = round(week_total_kcal / days, 1) if days else 0.0
            target_weekly = round(target_kcal * 7, 1) if target_kcal else None
            adherence_pct: float | None = None
            if target_weekly and target_weekly > 0:
                adherence_pct = round(min(week_total_kcal / target_weekly * 100, 200), 1)

            results.append(
                {
                    "week_label": (
                        f"{effective_start.strftime('%d/%m')} "
                        f"– {effective_end.strftime('%d/%m/%Y')}"
                    ),
                    "week_start": effective_start.isoformat(),
                    "week_end":   effective_end.isoformat(),
                    "meal_count":       int(match["meal_count"]) if match else 0,
                    "days_logged":      days,
                    "total_calories":   week_total_kcal,
                    "avg_daily_calories": avg_daily,
                    "target_weekly_kcal": target_weekly,
                    "adherence_pct":    adherence_pct,
                    "total_protein_g":  float(match["total_protein_g"]) if match else 0.0,
                    "total_fat_g":      float(match["total_fat_g"]) if match else 0.0,
                    "total_carb_g":     float(match["total_carb_g"]) if match else 0.0,
                }
            )
            cursor += timedelta(weeks=1)

        return results

    # ------------------------------------------------------------------
    # Progress stats – monthly
    # ------------------------------------------------------------------

    def monthly_stats(
        self,
        user_id: int,
        *,
        start: date,
        end: date,    # inclusive
    ) -> list[dict[str, Any]]:
        """Aggregate daily meal_logs into monthly buckets for [start, end].

        Partial months at range boundaries are included.
        Each month shows totals even when days_logged == 0 (all zeros).

        Returns list of monthly summary dicts ordered oldest→newest.
        """
        self.initialize_schema()
        end_excl = end + timedelta(days=1)
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end_excl, time.min)

        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            cur.execute("SELECT target_calories FROM users WHERE id = %s", (user_id,))
            user_row = cur.fetchone()
            if user_row is None:
                raise UserNotFoundError(f"User {user_id} does not exist")
            target_kcal: float | None = (
                float(user_row["target_calories"]) if user_row["target_calories"] else None
            )

            cur.execute(
                """
                SELECT
                    DATE_TRUNC('month', consumed_at)::date AS month_start,
                    COUNT(*)                               AS meal_count,
                    ROUND(SUM(total_calories)::numeric, 1) AS total_calories,
                    ROUND(SUM(COALESCE(protein_g, 0))::numeric, 1) AS total_protein_g,
                    ROUND(SUM(COALESCE(fat_g,     0))::numeric, 1) AS total_fat_g,
                    ROUND(SUM(COALESCE(carb_g,    0))::numeric, 1) AS total_carb_g,
                    COUNT(DISTINCT consumed_at::date)               AS days_logged
                FROM meal_logs
                WHERE user_id = %s
                  AND consumed_at >= %s
                  AND consumed_at <  %s
                GROUP BY month_start
                ORDER BY month_start
                """,
                (user_id, start_dt, end_dt),
            )
            rows = {r["month_start"]: dict(r) for r in cur.fetchall()}

        # Walk month-by-month from start's month to end's month
        results: list[dict[str, Any]] = []
        m_start = start.replace(day=1)
        while m_start <= end:
            nm = m_start.month % 12 + 1
            ny = m_start.year + (1 if m_start.month == 12 else 0)
            m_end_excl = date(ny, nm, 1)
            days_in_month = (m_end_excl - m_start).days
            effective_start = max(m_start, start)
            effective_end = min(m_end_excl - timedelta(days=1), end)
            match = rows.get(m_start)

            month_total_kcal = float(match["total_calories"]) if match else 0.0
            days = int(match["days_logged"]) if match else 0
            avg_daily = round(month_total_kcal / days, 1) if days else 0.0
            target_monthly = round(target_kcal * days_in_month, 1) if target_kcal else None
            adherence_pct: float | None = None
            if target_monthly and target_monthly > 0:
                adherence_pct = round(min(month_total_kcal / target_monthly * 100, 200), 1)

            results.append(
                {
                    "month_label":    effective_start.strftime("%Y-%m"),
                    "month_start":    effective_start.isoformat(),
                    "days_in_month":  days_in_month,
                    "meal_count":     int(match["meal_count"]) if match else 0,
                    "days_logged":    days,
                    "total_calories": month_total_kcal,
                    "avg_daily_calories": avg_daily,
                    "target_monthly_kcal": target_monthly,
                    "adherence_pct":  adherence_pct,
                    "total_protein_g": float(match["total_protein_g"]) if match else 0.0,
                    "total_fat_g":    float(match["total_fat_g"]) if match else 0.0,
                    "total_carb_g":   float(match["total_carb_g"]) if match else 0.0,
                }
            )
            m_start = m_end_excl

        return results


def _dict_cursor(connection: Any) -> Any:
    from psycopg2.extras import RealDictCursor

    return connection.cursor(cursor_factory=RealDictCursor)
