"""Diary API – photo-grid endpoints.

GET /api/v1/diary/weekly
    Params: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
    Trả lưới ảnh nhóm theo tuần trong khoảng [start_date, end_date].
    Chỉ trả về những ngày có bữa ăn trong mảng days[].

GET /api/v1/diary/monthly
    Params: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
    Trả lưới ảnh nhóm theo tháng trong khoảng [start_date, end_date].
    Chỉ trả về những ngày có bữa ăn trong mảng days[].

Response mỗi ô ngày (DayCell):
  - date                     ISO date string (YYYY-MM-DD)
  - meal_count               int
  - total_kcal               float
  - representative_image_url str | null  ← ảnh bữa ăn gần nhất có image_url
  - day_label                str  (weekly only: "T2"…"CN")

Response summary (footer):
  - streak_days              số ngày liên tiếp có log tính từ hôm nay về trước
  - total_meals_logged       tổng bữa ăn từ trước đến nay ("Locket Calo")
  - avg_daily_kcal           trung bình kcal/ngày (chỉ tính ngày CÓ ăn)
  - avg_daily_protein_g / fat_g / carb_g  macro footer
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..core.database import get_database
from ..repositories.diary import DiaryRepository
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/diary", tags=["diary"])

BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")

_MAX_RANGE_DAYS = 366  # guard against huge ranges


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class DayCellResponse(BaseModel):
    """Một ô ngày trong lưới – chỉ xuất hiện khi ngày đó có bữa ăn."""

    date: str
    meal_count: int
    total_kcal: float
    representative_image_url: str | None


class DayCellWithLabelResponse(DayCellResponse):
    """Như DayCellResponse + nhãn thứ trong tuần (T2…CN)."""

    day_label: str


class WeeklyDiaryItem(BaseModel):
    week_label: str        # "Tuần 01/11 – 07/11/2026"
    week_start: str        # ISO date – thứ Hai của tuần
    week_end: str          # ISO date – Chủ Nhật của tuần
    days_logged: int       # số ngày CÓ bữa ăn trong tuần
    total_kcal: float
    avg_daily_kcal: float  # trung bình trên các ngày CÓ ăn
    days: list[DayCellWithLabelResponse]   # chỉ ngày có bữa ăn


class MonthlyDiaryItem(BaseModel):
    month_label: str       # "tháng 10 2026"
    month_start: str       # ISO date – ngày 1 của tháng
    days_in_month: int     # tổng số ngày trong tháng (28/29/30/31)
    days_logged: int       # số ngày CÓ bữa ăn
    total_kcal: float
    avg_daily_kcal: float  # trung bình trên các ngày CÓ ăn
    days: list[DayCellResponse]   # chỉ ngày có bữa ăn


class DiaryWeeklyResponse(BaseModel):
    user_id: int
    start_date: str
    end_date: str
    streak_days: int
    total_meals_logged: int    # hiển thị là "Locket Calo"
    avg_daily_kcal: float
    avg_daily_protein_g: float
    avg_daily_fat_g: float
    avg_daily_carb_g: float
    data: list[WeeklyDiaryItem]


class DiaryMonthlyResponse(BaseModel):
    user_id: int
    start_date: str
    end_date: str
    streak_days: int
    total_meals_logged: int    # hiển thị là "Locket Calo"
    avg_daily_kcal: float
    avg_daily_protein_g: float
    avg_daily_fat_g: float
    avg_daily_carb_g: float
    data: list[MonthlyDiaryItem]


# ---------------------------------------------------------------------------
# Shared helper – parse & validate date params
# ---------------------------------------------------------------------------


def _parse_date(value: str, param_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{param_name}' phải có dạng YYYY-MM-DD, nhận được: '{value}'",
        )


def _validated_range(start_str: str, end_str: str) -> tuple[date, date]:
    """Parse, validate và trả (start, end) inclusive."""
    start = _parse_date(start_str, "start_date")
    end = _parse_date(end_str, "end_date")
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'end_date' phải >= 'start_date'.",
        )
    if (end - start).days >= _MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Khoảng thời gian tối đa là {_MAX_RANGE_DAYS} ngày.",
        )
    return start, end


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_diary_repo() -> DiaryRepository:
    return DiaryRepository(get_database())


# ---------------------------------------------------------------------------
# GET /api/v1/diary/weekly
# ---------------------------------------------------------------------------


@router.get(
    "/weekly",
    response_model=DiaryWeeklyResponse,
    summary="Nhật ký bữa ăn theo tuần (tab Tuần)",
    description=(
        "Trả về lưới ảnh nhóm theo tuần trong khoảng [start_date, end_date]. "
        "Chỉ những ngày có bữa ăn mới xuất hiện trong mảng days[]. "
        "Footer summary gồm streak, Locket Calo (tổng bữa), macro trung bình."
    ),
)
def weekly_diary(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[DiaryRepository, Depends(get_diary_repo)],
    start_date: Annotated[
        str,
        Query(description="Ngày bắt đầu (YYYY-MM-DD), ví dụ: 2026-10-27"),
    ],
    end_date: Annotated[
        str,
        Query(description="Ngày kết thúc (YYYY-MM-DD), ví dụ: 2026-11-02"),
    ],
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    start, end = _validated_range(start_date, end_date)
    today = datetime.now(BANGKOK_TIMEZONE).date()
    try:
        return repo.weekly_diary(user_id, start=start, end=end, today=today)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Diary weekly error for user %s", user_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Diary service temporarily unavailable",
        ) from exc


# ---------------------------------------------------------------------------
# GET /api/v1/diary/monthly
# ---------------------------------------------------------------------------


@router.get(
    "/monthly",
    response_model=DiaryMonthlyResponse,
    summary="Nhật ký bữa ăn theo tháng (tab Tháng)",
    description=(
        "Trả về lưới ảnh nhóm theo tháng trong khoảng [start_date, end_date]. "
        "Chỉ những ngày có bữa ăn mới xuất hiện trong mảng days[]. "
        "Footer summary gồm streak, Locket Calo (tổng bữa), macro trung bình."
    ),
)
def monthly_diary(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[DiaryRepository, Depends(get_diary_repo)],
    start_date: Annotated[
        str,
        Query(description="Ngày bắt đầu (YYYY-MM-DD), ví dụ: 2026-10-01"),
    ],
    end_date: Annotated[
        str,
        Query(description="Ngày kết thúc (YYYY-MM-DD), ví dụ: 2026-11-04"),
    ],
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    start, end = _validated_range(start_date, end_date)
    today = datetime.now(BANGKOK_TIMEZONE).date()
    try:
        return repo.monthly_diary(user_id, start=start, end=end, today=today)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Diary monthly error for user %s", user_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Diary service temporarily unavailable",
        ) from exc
