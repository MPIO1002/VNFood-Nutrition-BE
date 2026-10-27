"""Repository: user profile CRUD and progress / weight-log queries.

Tables used:
    users           – profile fields (weight, height, bmi, target_calories …)
    weight_logs     – history of weight updates (created by migration 0007)
    meal_logs       – daily intake aggregates for progress stats
"""
from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.database import PostgresDatabase

_WEIGHT_SCHEMA = """
CREATE TABLE IF NOT EXISTS weight_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weight_kg   DOUBLE PRECISION NOT NULL CHECK (weight_kg > 0 AND weight_kg <= 700),
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_weight_logs_user_id
    ON weight_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_weight_logs_recorded_at
    ON weight_logs(user_id, recorded_at DESC);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;
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
    # Profile update (avatar, full_name)
    # ------------------------------------------------------------------

    def update_profile(
        self,
        user_id: int,
        *,
        full_name: str | None = None,
        avatar_url: str | None = None,
    ) -> dict[str, Any]:
        """Update display name and/or avatar URL. Returns updated profile."""
        self.initialize_schema()
        fields: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
        values: list[Any] = []

        if full_name is not None:
            fields.append("full_name = %s")
            values.append(full_name)
        if avatar_url is not None:
            fields.append("avatar_url = %s")
            values.append(avatar_url)

        if len(fields) == 1:
            # Nothing to update – just return existing profile
            return self.get_profile(user_id)

        values.append(user_id)
        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
        with self.database.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, values)
            if cur.rowcount != 1:
                raise UserNotFoundError(f"User {user_id} does not exist")
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
        """Insert a new weight measurement and update users.weight.

        Returns the newly created weight_log row.
        """
        self.initialize_schema()
        recorded_at = recorded_at or datetime.utcnow()
        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            # Insert weight log entry
            cur.execute(
                """
                INSERT INTO weight_logs (user_id, weight_kg, recorded_at, note)
                VALUES (%s, %s, %s, %s)
                RETURNING id, user_id, weight_kg, recorded_at, note
                """,
                (user_id, weight_kg, recorded_at, note),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to insert weight log")

            # Keep users.weight in sync with the latest measurement
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

        return dict(row)

    # ------------------------------------------------------------------
    # Weight log – read history
    # ------------------------------------------------------------------

    def get_weight_history(
        self,
        user_id: int,
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Return the most recent *limit* weight log entries (newest first)."""
        self.initialize_schema()
        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT id, user_id, weight_kg, recorded_at, note
                FROM weight_logs
                WHERE user_id = %s
                ORDER BY recorded_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Progress stats – weekly
    # ------------------------------------------------------------------

    def weekly_stats(
        self,
        user_id: int,
        *,
        weeks: int = 4,
        reference_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate daily meal_logs into weekly buckets.

        Args:
            user_id: ID of the requesting user.
            weeks: How many past weeks to return (max 52).
            reference_date: Anchor date; defaults to today (UTC+7).

        Returns:
            List of weekly summary dicts, newest week first.
        """
        self.initialize_schema()
        weeks = min(max(weeks, 1), 52)
        ref = reference_date or date.today()

        # Align to the start of the current week (Monday)
        week_start = ref - timedelta(days=ref.weekday())
        # We want 'weeks' full weeks ending *before* current week
        # plus the current (possibly partial) week as week index 0.
        period_start = week_start - timedelta(weeks=weeks - 1)

        start_dt = datetime.combine(period_start, time.min)
        end_dt = datetime.combine(week_start + timedelta(days=7), time.min)

        with self.database.connection() as conn, _dict_cursor(conn) as cur:
            # Fetch target_calories for user
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
                    ROUND(AVG(total_calories)::numeric, 1) AS avg_calories_per_meal,
                    ROUND(SUM(COALESCE(protein_g, 0))::numeric, 1) AS total_protein_g,
                    ROUND(SUM(COALESCE(fat_g,     0))::numeric, 1) AS total_fat_g,
                    ROUND(SUM(COALESCE(carb_g,    0))::numeric, 1) AS total_carb_g,
                    COUNT(DISTINCT consumed_at::date)               AS days_logged
                FROM meal_logs
                WHERE user_id = %s
                  AND consumed_at >= %s
                  AND consumed_at <  %s
                GROUP BY week_start
                ORDER BY week_start DESC
                """,
                (user_id, start_dt, end_dt),
            )
            rows = [dict(r) for r in cur.fetchall()]

        # Build a full calendar of weeks so gaps show as zeros
        results: list[dict[str, Any]] = []
        for i in range(weeks - 1, -1, -1):
            w_start = week_start - timedelta(weeks=i)
            w_end = w_start + timedelta(days=6)
            match = next((r for r in rows if r["week_start"] == w_start), None)

            week_total_kcal = float(match["total_calories"]) if match else 0.0
            days = int(match["days_logged"]) if match else 0
            avg_daily = round(week_total_kcal / days, 1) if days else 0.0
            target_weekly = round(target_kcal * 7, 1) if target_kcal else None
            adherence_pct: float | None = None
            if target_weekly and target_weekly > 0:
                adherence_pct = round(min(week_total_kcal / target_weekly * 100, 200), 1)

            results.append(
                {
                    "week_label": f"{w_start.isoformat()} / {w_end.isoformat()}",
                    "week_start": w_start.isoformat(),
                    "week_end": w_end.isoformat(),
                    "meal_count": int(match["meal_count"]) if match else 0,
                    "days_logged": days,
                    "total_calories": week_total_kcal,
                    "avg_daily_calories": avg_daily,
                    "target_weekly_kcal": target_weekly,
                    "adherence_pct": adherence_pct,
                    "total_protein_g": float(match["total_protein_g"]) if match else 0.0,
                    "total_fat_g": float(match["total_fat_g"]) if match else 0.0,
                    "total_carb_g": float(match["total_carb_g"]) if match else 0.0,
                }
            )

        # Newest week first
        results.reverse()
        return results

    # ------------------------------------------------------------------
    # Progress stats – monthly
    # ------------------------------------------------------------------

    def monthly_stats(
        self,
        user_id: int,
        *,
        months: int = 3,
        reference_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate daily meal_logs into monthly buckets.

        Args:
            user_id: ID of the requesting user.
            months: How many past months to return (max 24).
            reference_date: Anchor date; defaults to today.

        Returns:
            List of monthly summary dicts, newest month first.
        """
        self.initialize_schema()
        months = min(max(months, 1), 24)
        ref = reference_date or date.today()

        # Determine the start of the period
        # Go back (months - 1) full months from the current month
        current_month_start = ref.replace(day=1)
        period_start_year = current_month_start.year
        period_start_month = current_month_start.month - (months - 1)
        while period_start_month <= 0:
            period_start_month += 12
            period_start_year -= 1
        period_start = date(period_start_year, period_start_month, 1)

        # End: first day of next month after ref
        next_month = current_month_start.month % 12 + 1
        next_month_year = current_month_start.year + (1 if current_month_start.month == 12 else 0)
        period_end = date(next_month_year, next_month, 1)

        start_dt = datetime.combine(period_start, time.min)
        end_dt = datetime.combine(period_end, time.min)

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
                    ROUND(AVG(total_calories)::numeric, 1) AS avg_calories_per_meal,
                    ROUND(SUM(COALESCE(protein_g, 0))::numeric, 1) AS total_protein_g,
                    ROUND(SUM(COALESCE(fat_g,     0))::numeric, 1) AS total_fat_g,
                    ROUND(SUM(COALESCE(carb_g,    0))::numeric, 1) AS total_carb_g,
                    COUNT(DISTINCT consumed_at::date)               AS days_logged
                FROM meal_logs
                WHERE user_id = %s
                  AND consumed_at >= %s
                  AND consumed_at <  %s
                GROUP BY month_start
                ORDER BY month_start DESC
                """,
                (user_id, start_dt, end_dt),
            )
            rows = [dict(r) for r in cur.fetchall()]

        # Build full calendar of months
        results: list[dict[str, Any]] = []
        for i in range(months - 1, -1, -1):
            m_year = current_month_start.year
            m_month = current_month_start.month - i
            while m_month <= 0:
                m_month += 12
                m_year -= 1
            m_start = date(m_year, m_month, 1)
            match = next((r for r in rows if r["month_start"] == m_start), None)

            month_total_kcal = float(match["total_calories"]) if match else 0.0
            days = int(match["days_logged"]) if match else 0

            # Days in month
            if m_month == 12:
                days_in_month = (date(m_year + 1, 1, 1) - m_start).days
            else:
                days_in_month = (date(m_year, m_month + 1, 1) - m_start).days

            avg_daily = round(month_total_kcal / days, 1) if days else 0.0
            target_monthly = round(target_kcal * days_in_month, 1) if target_kcal else None
            adherence_pct: float | None = None
            if target_monthly and target_monthly > 0:
                adherence_pct = round(min(month_total_kcal / target_monthly * 100, 200), 1)

            results.append(
                {
                    "month_label": m_start.strftime("%Y-%m"),
                    "month_start": m_start.isoformat(),
                    "days_in_month": days_in_month,
                    "meal_count": int(match["meal_count"]) if match else 0,
                    "days_logged": days,
                    "total_calories": month_total_kcal,
                    "avg_daily_calories": avg_daily,
                    "target_monthly_kcal": target_monthly,
                    "adherence_pct": adherence_pct,
                    "total_protein_g": float(match["total_protein_g"]) if match else 0.0,
                    "total_fat_g": float(match["total_fat_g"]) if match else 0.0,
                    "total_carb_g": float(match["total_carb_g"]) if match else 0.0,
                }
            )

        results.reverse()
        return results


def _dict_cursor(connection: Any) -> Any:
    from psycopg2.extras import RealDictCursor

    return connection.cursor(cursor_factory=RealDictCursor)
