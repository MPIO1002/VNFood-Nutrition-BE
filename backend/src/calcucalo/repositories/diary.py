"""Repository: Diary photo-grid queries.

Cung cấp dữ liệu cho 2 API:
  GET /api/v1/diary/weekly   – lưới ảnh nhóm theo tuần
  GET /api/v1/diary/monthly  – lưới ảnh nhóm theo tháng

Hành vi mới (v2):
  - Nhận start/end date thay vì số tuần/tháng.
  - Chỉ trả những ngày CÓ bữa ăn trong mảng days[].
    Ngày không có meal không xuất hiện → has_meals field bị bỏ.
  - avg_daily_kcal tính trên ngày có ăn, không chia đều toàn kỳ.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from ..core.database import PostgresDatabase


class DiaryRepository:
    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_daily_data(
        self,
        user_id: int,
        start_date: date,
        end_date_excl: date,
    ) -> dict[date, dict[str, Any]]:
        """Fetch per-day aggregates (meals, kcal, macros, best image).

        Returns a dict keyed by date — only dates that HAVE meal logs.
        """
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date_excl, time.min)

        with self.database.connection() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        consumed_at::date                                        AS day,
                        COUNT(*)                                                 AS meal_count,
                        ROUND(SUM(total_calories)::numeric, 1)                  AS total_kcal,
                        ROUND(SUM(COALESCE(protein_g, 0))::numeric, 1)          AS total_protein_g,
                        ROUND(SUM(COALESCE(fat_g,     0))::numeric, 1)          AS total_fat_g,
                        ROUND(SUM(COALESCE(carb_g,    0))::numeric, 1)          AS total_carb_g,
                        -- Prefer images from the latest meal type; use time for ties.
                        (ARRAY_AGG(image_url ORDER BY
                            CASE LOWER(BTRIM(ml.meal_type))
                                WHEN 'breakfast' THEN 1
                                WHEN 'lunch' THEN 2
                                WHEN 'snack' THEN 3
                                WHEN 'dinner' THEN 4
                                ELSE 0
                            END DESC,
                            consumed_at DESC,
                            ml.id DESC
                        )
                        FILTER (WHERE image_url IS NOT NULL))[1]     AS representative_image_url
                    FROM meal_logs ml
                    WHERE user_id    = %s
                      AND consumed_at >= %s
                      AND consumed_at <  %s
                    GROUP BY consumed_at::date
                    ORDER BY day
                    """,
                    (user_id, start_dt, end_dt),
                )
                rows = cur.fetchall()

        return {
            row["day"]: {
                "meal_count":               int(row["meal_count"]),
                "total_kcal":               float(row["total_kcal"] or 0),
                "total_protein_g":          float(row["total_protein_g"] or 0),
                "total_fat_g":              float(row["total_fat_g"] or 0),
                "total_carb_g":             float(row["total_carb_g"] or 0),
                "representative_image_url": row["representative_image_url"],
            }
            for row in rows
        }

    def _streak_and_summary(
        self,
        user_id: int,
        today: date,
        start_date: date,
        end_date_excl: date,
    ) -> dict[str, Any]:
        """Compute streak (all-time) and period-wide summary stats."""
        with self.database.connection() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # All logged dates ever (for streak from today)
                cur.execute(
                    """
                    SELECT DISTINCT consumed_at::date AS log_date
                    FROM   meal_logs
                    WHERE  user_id = %s
                    ORDER  BY log_date DESC
                    """,
                    (user_id,),
                )
                all_dates = sorted(
                    {row["log_date"] for row in cur.fetchall()}, reverse=True
                )

                # Period totals (avg only over days that have meals)
                cur.execute(
                    """
                    SELECT
                        COUNT(*)                                    AS total_meals,
                        ROUND(AVG(daily_kcal)::numeric, 1)         AS avg_daily_kcal,
                        ROUND(AVG(daily_protein)::numeric, 1)      AS avg_daily_protein,
                        ROUND(AVG(daily_fat)::numeric, 1)          AS avg_daily_fat,
                        ROUND(AVG(daily_carb)::numeric, 1)         AS avg_daily_carb
                    FROM (
                        SELECT
                            consumed_at::date                       AS day,
                            SUM(total_calories)                     AS daily_kcal,
                            SUM(COALESCE(protein_g, 0))             AS daily_protein,
                            SUM(COALESCE(fat_g,     0))             AS daily_fat,
                            SUM(COALESCE(carb_g,    0))             AS daily_carb
                        FROM   meal_logs
                        WHERE  user_id = %s
                          AND  consumed_at >= %s
                          AND  consumed_at <  %s
                        GROUP  BY consumed_at::date
                    ) daily
                    """,
                    (user_id, datetime.combine(start_date, time.min),
                     datetime.combine(end_date_excl, time.min)),
                )
                totals = dict(cur.fetchone() or {})

                # Total meals ever (for "Locket Calo" badge)
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM meal_logs WHERE user_id = %s",
                    (user_id,),
                )
                total_meals_ever = int((cur.fetchone() or {}).get("cnt", 0))

        # Compute streak starting from today going backwards
        streak = 0
        check = today
        for d in all_dates:
            if d == check:
                streak += 1
                check = check - timedelta(days=1)
            elif d < check:
                break

        return {
            "streak_days":         streak,
            "total_meals_logged":  total_meals_ever,
            "avg_daily_kcal":      float(totals.get("avg_daily_kcal") or 0),
            "avg_daily_protein_g": float(totals.get("avg_daily_protein") or 0),
            "avg_daily_fat_g":     float(totals.get("avg_daily_fat") or 0),
            "avg_daily_carb_g":    float(totals.get("avg_daily_carb") or 0),
        }

    @staticmethod
    def _day_cell(d: date, row: dict[str, Any]) -> dict[str, Any]:
        """Build a day-cell dict from a row that IS known to have meals."""
        return {
            "date":                     d.isoformat(),
            "meal_count":               row["meal_count"],
            "total_kcal":               row["total_kcal"],
            "representative_image_url": row["representative_image_url"],
        }

    # ------------------------------------------------------------------
    # Weekly diary
    # ------------------------------------------------------------------

    def weekly_diary(
        self,
        user_id: int,
        *,
        start: date,
        end: date,       # inclusive
        today: date | None = None,
    ) -> dict[str, Any]:
        """Return diary grid grouped by week for [start, end] (inclusive).

        - Weeks are Mon-Sun. If start/end don't align to Mon/Sun the
          boundary week is partial (shows only days within range).
        - Only days with meal logs appear in days[].
        - avg_daily_kcal is averaged over days-with-meals only.
        """
        today = today or date.today()
        end_excl = end + timedelta(days=1)

        daily_data = self._fetch_daily_data(user_id, start, end_excl)
        summary = self._streak_and_summary(user_id, today, start, end_excl)

        # Walk from the Monday on-or-before `start` up to `end`
        week_monday = start - timedelta(days=start.weekday())
        VN_DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

        weeks_list: list[dict[str, Any]] = []
        cursor = week_monday
        while cursor <= end:
            w_start = cursor
            w_end = cursor + timedelta(days=6)
            # Clamp to requested range for label purposes
            effective_start = max(w_start, start)
            effective_end = min(w_end, end)

            # Build day cells — only days with data
            day_cells: list[dict[str, Any]] = []
            days_with_meals_in_week: list[date] = []
            for j in range(7):
                d = w_start + timedelta(days=j)
                if d < start or d > end:
                    continue        # outside requested range
                if d in daily_data:
                    cell = self._day_cell(d, daily_data[d])
                    cell["day_label"] = VN_DAYS[j]
                    day_cells.append(cell)
                    days_with_meals_in_week.append(d)

            week_kcal = sum(daily_data[d]["total_kcal"] for d in days_with_meals_in_week)
            avg_daily = (
                round(week_kcal / len(days_with_meals_in_week), 1)
                if days_with_meals_in_week else 0.0
            )

            weeks_list.append({
                "week_label":     (
                    f"Tuần {effective_start.strftime('%d/%m')} "
                    f"– {effective_end.strftime('%d/%m/%Y')}"
                ),
                "week_start":     effective_start.isoformat(),
                "week_end":       effective_end.isoformat(),
                "days_logged":    len(days_with_meals_in_week),
                "total_kcal":     round(week_kcal, 1),
                "avg_daily_kcal": avg_daily,
                "days":           day_cells,
            })

            cursor += timedelta(weeks=1)

        return {
            "user_id":             user_id,
            "start_date":          start.isoformat(),
            "end_date":            end.isoformat(),
            "streak_days":         summary["streak_days"],
            "total_meals_logged":  summary["total_meals_logged"],
            "avg_daily_kcal":      summary["avg_daily_kcal"],
            "avg_daily_protein_g": summary["avg_daily_protein_g"],
            "avg_daily_fat_g":     summary["avg_daily_fat_g"],
            "avg_daily_carb_g":    summary["avg_daily_carb_g"],
            "data":                weeks_list,
        }

    # ------------------------------------------------------------------
    # Monthly diary
    # ------------------------------------------------------------------

    def monthly_diary(
        self,
        user_id: int,
        *,
        start: date,
        end: date,       # inclusive
        today: date | None = None,
    ) -> dict[str, Any]:
        """Return diary grid grouped by calendar month for [start, end].

        - Only days with meal logs appear in days[].
        - avg_daily_kcal is averaged over days-with-meals only.
        """
        today = today or date.today()
        end_excl = end + timedelta(days=1)

        daily_data = self._fetch_daily_data(user_id, start, end_excl)
        summary = self._streak_and_summary(user_id, today, start, end_excl)

        VN_MONTHS = [
            "", "tháng 1", "tháng 2", "tháng 3", "tháng 4",
            "tháng 5", "tháng 6", "tháng 7", "tháng 8",
            "tháng 9", "tháng 10", "tháng 11", "tháng 12",
        ]

        # Walk month by month from start's month to end's month
        months_list: list[dict[str, Any]] = []
        m_start = start.replace(day=1)
        while m_start <= end:
            # end of this month (exclusive)
            nm = m_start.month % 12 + 1
            ny = m_start.year + (1 if m_start.month == 12 else 0)
            m_end_excl = date(ny, nm, 1)
            days_in_month = (m_end_excl - m_start).days

            # Clamp to requested range
            effective_start = max(m_start, start)
            effective_end = min(m_end_excl - timedelta(days=1), end)

            # Build day cells — only days with data within effective range
            day_cells: list[dict[str, Any]] = []
            days_with_meals: list[date] = []
            for j in range(days_in_month):
                d = m_start + timedelta(days=j)
                if d < effective_start or d > effective_end:
                    continue    # outside requested range
                if d in daily_data:
                    day_cells.append(self._day_cell(d, daily_data[d]))
                    days_with_meals.append(d)

            month_kcal = sum(daily_data[d]["total_kcal"] for d in days_with_meals)
            avg_daily = (
                round(month_kcal / len(days_with_meals), 1)
                if days_with_meals else 0.0
            )

            months_list.append({
                "month_label":   f"{VN_MONTHS[m_start.month]} {m_start.year}",
                "month_start":   effective_start.isoformat(),
                "days_in_month": days_in_month,
                "days_logged":   len(days_with_meals),
                "total_kcal":    round(month_kcal, 1),
                "avg_daily_kcal": avg_daily,
                "days":          day_cells,
            })

            m_start = m_end_excl   # advance to next month

        return {
            "user_id":             user_id,
            "start_date":          start.isoformat(),
            "end_date":            end.isoformat(),
            "streak_days":         summary["streak_days"],
            "total_meals_logged":  summary["total_meals_logged"],
            "avg_daily_kcal":      summary["avg_daily_kcal"],
            "avg_daily_protein_g": summary["avg_daily_protein_g"],
            "avg_daily_fat_g":     summary["avg_daily_fat_g"],
            "avg_daily_carb_g":    summary["avg_daily_carb_g"],
            "data":                months_list,
        }
