"""Repository: Diary photo-grid queries.

Cung cấp dữ liệu cho 2 API:
  GET /api/v1/diary/weekly   – lưới ảnh theo tuần
  GET /api/v1/diary/monthly  – lưới ảnh theo tháng

Mỗi ô lưới = 1 ngày:
  - representative_image_url: ảnh đầu tiên có trong ngày (hoặc null)
  - has_meals: True nếu có bữa ăn
  - total_kcal, meal_count
  - total_protein_g, total_fat_g, total_carb_g

Summary toàn màn hình:
  - streak_days: số ngày liên tiếp có ăn tính từ hôm nay
  - total_meals_logged: tổng bữa ăn đã log (hiển thị là "Locket Calo")
  - avg_protein_g / avg_carb_g / avg_fat_g: trung bình daily macro trong kỳ
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
        end_date: date,   # exclusive
    ) -> dict[date, dict[str, Any]]:
        """Fetch per-day aggregates (meals, kcal, macros, best image)."""
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.min)

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
                        -- Most recent non-null image for this day
                        (
                            SELECT ml2.image_url
                            FROM   meal_logs ml2
                            WHERE  ml2.user_id      = ml.user_id
                              AND  ml2.consumed_at::date = ml.consumed_at::date
                              AND  ml2.image_url    IS NOT NULL
                            ORDER  BY ml2.consumed_at DESC
                            LIMIT  1
                        ) AS representative_image_url
                    FROM meal_logs ml
                    WHERE user_id    = %s
                      AND consumed_at >= %s
                      AND consumed_at <  %s
                    GROUP BY consumed_at::date, ml.user_id
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
        end_date: date,   # exclusive
    ) -> dict[str, Any]:
        """Compute streak and period-wide summary stats."""
        with self.database.connection() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # All logged dates in period
                cur.execute(
                    """
                    SELECT DISTINCT consumed_at::date AS log_date
                    FROM   meal_logs
                    WHERE  user_id = %s
                      AND  consumed_at >= %s
                      AND  consumed_at <  %s
                    ORDER  BY log_date DESC
                    """,
                    (user_id, datetime.combine(start_date, time.min),
                     datetime.combine(end_date, time.min)),
                )
                period_dates = {row["log_date"] for row in cur.fetchall()}

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

                # Period totals
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
                            SUM(COALESCE(carb_g,    0))             AS daily_carb,
                            COUNT(*)                                AS meals_on_day
                        FROM   meal_logs
                        WHERE  user_id = %s
                          AND  consumed_at >= %s
                          AND  consumed_at <  %s
                        GROUP  BY consumed_at::date
                    ) daily
                    """,
                    (user_id, datetime.combine(start_date, time.min),
                     datetime.combine(end_date, time.min)),
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
    def _day_cell(d: date, data: dict[date, dict[str, Any]]) -> dict[str, Any]:
        row = data.get(d)
        if row:
            return {
                "date":                     d.isoformat(),
                "has_meals":                True,
                "meal_count":               row["meal_count"],
                "total_kcal":               row["total_kcal"],
                "representative_image_url": row["representative_image_url"],
            }
        return {
            "date":                     d.isoformat(),
            "has_meals":                False,
            "meal_count":               0,
            "total_kcal":               0.0,
            "representative_image_url": None,
        }

    # ------------------------------------------------------------------
    # Weekly diary
    # ------------------------------------------------------------------

    def weekly_diary(
        self,
        user_id: int,
        *,
        weeks: int = 4,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Return diary grid grouped by week.

        Each week contains 7 day-cells (Mon-Sun) with photo + kcal.
        Includes overall summary (streak, macros) across the entire period.
        """
        today = today or date.today()
        weeks = min(max(weeks, 1), 52)

        # Monday of current week
        week_start = today - timedelta(days=today.weekday())
        period_start = week_start - timedelta(weeks=weeks - 1)
        period_end = week_start + timedelta(days=7)   # exclusive

        daily_data = self._fetch_daily_data(user_id, period_start, period_end)
        summary = self._streak_and_summary(user_id, today, period_start, period_end)

        weeks_list: list[dict[str, Any]] = []
        for i in range(weeks - 1, -1, -1):
            w_start = week_start - timedelta(weeks=i)
            w_end = w_start + timedelta(days=6)       # inclusive Sunday

            days_with_meals = [
                d for d in (w_start + timedelta(days=j) for j in range(7))
                if d in daily_data
            ]
            week_kcal = sum(daily_data[d]["total_kcal"] for d in days_with_meals)
            avg_daily = (
                round(week_kcal / len(days_with_meals), 1)
                if days_with_meals else 0.0
            )

            # Vietnamese short day labels
            VN_DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
            day_cells = []
            for j in range(7):
                d = w_start + timedelta(days=j)
                cell = self._day_cell(d, daily_data)
                cell["day_label"] = VN_DAYS[j]
                day_cells.append(cell)

            weeks_list.append({
                "week_label":    f"Tuần {weeks - i} · {w_start.strftime('%d/%m')} – {w_end.strftime('%d/%m/%Y')}",
                "week_start":    w_start.isoformat(),
                "week_end":      w_end.isoformat(),
                "days_logged":   len(days_with_meals),
                "total_kcal":    round(week_kcal, 1),
                "avg_daily_kcal": avg_daily,
                "days":          day_cells,
            })

        return {
            "user_id":            user_id,
            "weeks":              weeks,
            "streak_days":        summary["streak_days"],
            "total_meals_logged": summary["total_meals_logged"],
            "avg_daily_kcal":     summary["avg_daily_kcal"],
            "avg_daily_protein_g": summary["avg_daily_protein_g"],
            "avg_daily_fat_g":    summary["avg_daily_fat_g"],
            "avg_daily_carb_g":   summary["avg_daily_carb_g"],
            "data":               weeks_list,
        }

    # ------------------------------------------------------------------
    # Monthly diary
    # ------------------------------------------------------------------

    def monthly_diary(
        self,
        user_id: int,
        *,
        months: int = 2,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Return diary grid grouped by calendar month.

        Each month contains one cell per calendar day with photo + kcal.
        Includes overall summary (streak, macros) across the entire period.
        """
        today = today or date.today()
        months = min(max(months, 1), 24)

        current_month_start = today.replace(day=1)

        # Compute period_start (first day of oldest month)
        y = current_month_start.year
        m = current_month_start.month - (months - 1)
        while m <= 0:
            m += 12
            y -= 1
        period_start = date(y, m, 1)

        # period_end = first day of next month after today
        nm = current_month_start.month % 12 + 1
        ny = current_month_start.year + (1 if current_month_start.month == 12 else 0)
        period_end = date(ny, nm, 1)

        daily_data = self._fetch_daily_data(user_id, period_start, period_end)
        summary = self._streak_and_summary(user_id, today, period_start, period_end)

        months_list: list[dict[str, Any]] = []
        for i in range(months - 1, -1, -1):
            my = current_month_start.year
            mm = current_month_start.month - i
            while mm <= 0:
                mm += 12
                my -= 1
            m_start = date(my, mm, 1)

            # Days in month
            next_m = mm % 12 + 1
            next_y = my + (1 if mm == 12 else 0)
            m_end_excl = date(next_y, next_m, 1)
            days_in_month = (m_end_excl - m_start).days

            days_with_meals = [
                m_start + timedelta(days=j)
                for j in range(days_in_month)
                if (m_start + timedelta(days=j)) in daily_data
            ]
            month_kcal = sum(daily_data[d]["total_kcal"] for d in days_with_meals)
            avg_daily = (
                round(month_kcal / len(days_with_meals), 1)
                if days_with_meals else 0.0
            )

            day_cells = [
                self._day_cell(m_start + timedelta(days=j), daily_data)
                for j in range(days_in_month)
            ]

            # Vietnamese month header: "tháng 10 2026"
            VN_MONTHS = [
                "", "tháng 1", "tháng 2", "tháng 3", "tháng 4",
                "tháng 5", "tháng 6", "tháng 7", "tháng 8",
                "tháng 9", "tháng 10", "tháng 11", "tháng 12",
            ]
            month_label = f"{VN_MONTHS[mm]} {my}"

            months_list.append({
                "month_label":   month_label,
                "month_start":   m_start.isoformat(),
                "days_in_month": days_in_month,
                "days_logged":   len(days_with_meals),
                "total_kcal":    round(month_kcal, 1),
                "avg_daily_kcal": avg_daily,
                "days":          day_cells,
            })

        return {
            "user_id":             user_id,
            "months":              months,
            "streak_days":         summary["streak_days"],
            "total_meals_logged":  summary["total_meals_logged"],
            "avg_daily_kcal":      summary["avg_daily_kcal"],
            "avg_daily_protein_g": summary["avg_daily_protein_g"],
            "avg_daily_fat_g":     summary["avg_daily_fat_g"],
            "avg_daily_carb_g":    summary["avg_daily_carb_g"],
            "data":                months_list,
        }

