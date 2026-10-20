from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.database import get_database
from ..repositories.nutrition_tracking import (
    DishNotFoundError,
    NutritionTrackingRepository,
    UserNotFoundError,
)
from ..services.metabolism import MetabolismResult, calculate_metabolism
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["nutrition and meals"])
# Bangkok has used UTC+07:00 year-round since 1920. A fixed offset keeps the
# API portable on Windows installations that do not ship the IANA tz database.
BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class NutritionGoal(str, Enum):
    LOSE_WEIGHT = "lose_weight"
    MAINTAIN_WEIGHT = "maintain_weight"
    GAIN_WEIGHT = "gain_weight"


class MetabolismRequest(BaseModel):
    gender: Gender
    age: int = Field(ge=18, le=120)
    height_cm: float = Field(gt=100, le=250, allow_inf_nan=False)
    weight_kg: float = Field(gt=25, le=400, allow_inf_nan=False)
    activity_level: ActivityLevel
    goal: NutritionGoal


class MetabolismResponse(BaseModel):
    user_id: int
    gender: Gender
    age: int
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    goal: NutritionGoal
    bmi: float
    bmi_category: str
    bmr_kcal_per_day: float
    activity_factor: float
    tdee_kcal_per_day: float
    goal_adjustment_kcal: float
    target_kcal_per_day: float


class MealCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    dish_id: int | None = Field(default=None, gt=0)
    meal_type: str = Field(min_length=1, max_length=50)
    quantity: float = Field(default=1.0, gt=0, le=100, allow_inf_nan=False)
    total_calories: float = Field(ge=0, le=20_000, allow_inf_nan=False)
    image_url: str | None = Field(default=None, max_length=2048)
    consumed_at: datetime | None = None

    @field_validator("image_url")
    @classmethod
    def empty_image_url_is_none(cls, value: str | None) -> str | None:
        return value or None


class MealResponse(BaseModel):
    id: int
    user_id: int
    dish_id: int | None
    dish_name: str | None
    meal_type: str
    quantity: float
    total_calories: float
    image_url: str | None
    consumed_at: datetime
    created_at: datetime
    updated_at: datetime


class DailyMealsResponse(BaseModel):
    date: date
    timezone: str = "Asia/Bangkok"
    meal_count: int
    total_calories: float
    target_kcal_per_day: float | None
    remaining_kcal: float | None
    meals: list[MealResponse]


def get_nutrition_tracking_repository() -> NutritionTrackingRepository:
    return NutritionTrackingRepository(get_database())


@router.post("/nutrition/calculate", response_model=MetabolismResponse)
def calculate_daily_nutrition(
    request: MetabolismRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repository: Annotated[
        NutritionTrackingRepository, Depends(get_nutrition_tracking_repository)
    ],
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    result = calculate_metabolism(
        gender=request.gender.value,
        age=request.age,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        activity_level=request.activity_level.value,
        goal=request.goal.value,
    )
    try:
        repository.update_metabolism_profile(
            user_id=user_id,
            gender=request.gender.value,
            age=request.age,
            height_cm=request.height_cm,
            weight_kg=request.weight_kg,
            activity_level=request.activity_level.value,
            goal=request.goal.value,
            bmi=result.bmi,
            tdee=result.tdee_kcal_per_day,
            target_calories=result.target_kcal_per_day,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_unavailable(exc) from exc

    return {
        "user_id": user_id,
        **request.model_dump(),
        **_metabolism_payload(result),
    }


@router.post("/meals", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
def create_meal(
    request: MealCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repository: Annotated[
        NutritionTrackingRepository, Depends(get_nutrition_tracking_repository)
    ],
) -> dict[str, Any]:
    try:
        return repository.create_meal_log(
            user_id=int(current_user["id"]),
            dish_id=request.dish_id,
            meal_type=request.meal_type,
            quantity=request.quantity,
            total_calories=request.total_calories,
            image_url=request.image_url,
            consumed_at=_as_bangkok_naive(request.consumed_at),
        )
    except DishNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_unavailable(exc) from exc


@router.get("/meals/daily", response_model=DailyMealsResponse)
def get_daily_meals(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repository: Annotated[
        NutritionTrackingRepository, Depends(get_nutrition_tracking_repository)
    ],
    requested_date: Annotated[date | None, Query(alias="date")] = None,
) -> dict[str, Any]:
    day = requested_date or datetime.now(BANGKOK_TIMEZONE).date()
    try:
        meals, target = repository.daily_meals(user_id=int(current_user["id"]), day=day)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_unavailable(exc) from exc

    total = round(sum(float(meal["total_calories"]) for meal in meals), 1)
    remaining = round(target - total, 1) if target is not None else None
    return {
        "date": day,
        "meal_count": len(meals),
        "total_calories": total,
        "target_kcal_per_day": target,
        "remaining_kcal": remaining,
        "meals": meals,
    }


def _as_bangkok_naive(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(BANGKOK_TIMEZONE).replace(tzinfo=None)
    if value.tzinfo is not None:
        return value.astimezone(BANGKOK_TIMEZONE).replace(tzinfo=None)
    return value


def _metabolism_payload(result: MetabolismResult) -> dict[str, Any]:
    return result.to_dict()


def _database_unavailable(exc: Exception) -> HTTPException:
    logger.error(
        "Nutrition tracking database operation failed",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Nutrition tracking service is temporarily unavailable",
    )
