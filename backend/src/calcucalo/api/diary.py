"""Diary API – photo-grid endpoints.

GET /api/v1/diary/weekly   – lưới ảnh theo tuần (dùng cho tab "Tuần")
GET /api/v1/diary/monthly  – lưới ảnh theo tháng (dùng cho tab "Tháng")

Response mỗi ô ngày (day cell):
  - date                     ISO date string
  - has_meals                bool
  - meal_count               int
  - total_kcal               float
  - representative_image_url str | null  ← ảnh hiển thị trên lưới
  - day_label                str  (weekly only: "T2"…"CN")

Response summary (footer):
  - streak_days              số ngày liên tiếp có log
  - total_meals_logged       tổng bữa ăn từ trước đến nay ("Locket Calo")
  - avg_daily_kcal           trung bình kcal/ngày trong kỳ
  - avg_daily_protein_g / fat_g / carb_g  macro footer
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..core.database import get_database
from ..repositories.diary import DiaryRepository
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/diary", tags=["diary"])

BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class DayCellResponse(BaseModel):
    date: str
    has_meals: bool
    meal_count: int
    total_kcal: float
    representative_image_url: str | None


class DayCellWithLabelResponse(DayCellResponse):
    day_label: str   # "T2" … "CN"


class WeeklyDiaryItem(BaseModel):
    week_label: str
    week_start: str
    week_end: str
    days_logged: int
    total_kcal: float
    avg_daily_kcal: float
    days: list[DayCellWithLabelResponse]


class MonthlyDiaryItem(BaseModel):
    month_label: str          # "tháng 10 2026"
    month_start: str
    days_in_month: int
    days_logged: int
    total_kcal: float
    avg_daily_kcal: float
    days: list[DayCellResponse]


class DiaryWeeklyResponse(BaseModel):
    user_id: int
    weeks: int
    streak_days: int
    total_meals_logged: int   # hiển thị là "Locket Calo"
    avg_daily_kcal: float
    avg_daily_protein_g: float
    avg_daily_fat_g: float
    avg_daily_carb_g: float
    data: list[WeeklyDiaryItem]


class DiaryMonthlyResponse(BaseModel):
    user_id: int
    months: int
    streak_days: int
    total_meals_logged: int   # hiển thị là "Locket Calo"
    avg_daily_kcal: float
    avg_daily_protein_g: float
    avg_daily_fat_g: float
    avg_daily_carb_g: float
    data: list[MonthlyDiaryItem]


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
        "Trả về lưới ảnh 7 ngày/tuần cho tab 'Tuần' trong màn hình Nhật ký. "
        "Mỗi ô ngày chứa ảnh đại diện (ảnh bữa ăn đầu tiên có image_url), "
        "tổng kcal và số bữa. "
        "Footer summary gồm streak, Locket Calo (tổng bữa), macro trung bình."
    ),
)
def weekly_diary(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[DiaryRepository, Depends(get_diary_repo)],
    weeks: Annotated[
        int,
        Query(ge=1, le=52, description="Số tuần cần lấy (mặc định 4)"),
    ] = 4,
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    today = datetime.now(BANGKOK_TIMEZONE).date()
    try:
        return repo.weekly_diary(user_id, weeks=weeks, today=today)
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
        "Trả về lưới ảnh theo từng ngày trong tháng cho tab 'Tháng'. "
        "Mỗi tháng chứa đủ số ô theo số ngày trong tháng; "
        "ô trống (không có bữa ăn) trả về has_meals=false, image_url=null. "
        "Header mỗi tháng: avg_daily_kcal. "
        "Footer summary: streak_days, total_meals_logged, macro trung bình."
    ),
)
def monthly_diary(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[DiaryRepository, Depends(get_diary_repo)],
    months: Annotated[
        int,
        Query(ge=1, le=24, description="Số tháng cần lấy (mặc định 2)"),
    ] = 2,
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    today = datetime.now(BANGKOK_TIMEZONE).date()
    try:
        return repo.monthly_diary(user_id, months=months, today=today)
    except Exception as exc:
        logger.error("Diary monthly error for user %s", user_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Diary service temporarily unavailable",
        ) from exc

