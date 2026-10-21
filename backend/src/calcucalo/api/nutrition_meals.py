from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.database import get_database
from ..repositories.nutrition_tracking import (
    DishNotFoundError,
    DishNutritionUnavailableError,
    MealCalorieLimitError,
    NutritionTrackingRepository,
    UserNotFoundError,
)
from ..services.metabolism import (
    MetabolismResult,
    UnsafeCalorieTargetError,
    UnsupportedMetabolismProfileError,
    calculate_metabolism,
)
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["nutrition and meals"])
# Bangkok has used UTC+07:00 year-round since 1920. A fixed offset keeps the
# API portable on Windows installations that do not ship the IANA tz database.
BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")


class SexForEquation(str, Enum):
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


class GoalPace(str, Enum):
    GRADUAL = "gradual"
    STANDARD = "standard"


class CalorieSource(str, Enum):
    DISH_CATALOG = "dish_catalog"
    MANUAL = "manual"


class MetabolismRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sex_for_equation: SexForEquation = Field(
        validation_alias=AliasChoices("sex_for_equation", "gender"),
        description=(
            "Biological sex constant used by Mifflin-St Jeor. "
            "The legacy input name 'gender' is also accepted."
        ),
    )
    age: int = Field(ge=18, le=120)
    height_cm: float = Field(gt=100, le=250, allow_inf_nan=False)
    weight_kg: float = Field(gt=25, le=400, allow_inf_nan=False)
    activity_level: ActivityLevel = Field(
        description=(
            "sedentary: little exercise; light: 1-3 days/week; moderate: 3-5; "
            "active: 6-7; very_active: hard training or physical work"
        )
    )
    goal: NutritionGoal = Field(description="Lose, maintain, or gain weight")
    goal_pace: GoalPace | None = Field(
        default=None,
        description=(
            "gradual applies 250 kcal/day and standard applies 500 kcal/day; "
            "omit for maintain_weight"
        ),
    )
    pregnant_or_breastfeeding: bool = Field(
        default=False, description="True makes this general estimator return 422"
    )
    competitive_athlete: bool = Field(
        default=False, description="True makes this general estimator return 422"
    )
    metabolism_affecting_condition: bool = Field(
        default=False,
        description="A relevant medical condition or medication; true returns 422",
    )

    @model_validator(mode="after")
    def validate_goal_pace(self) -> MetabolismRequest:
        if self.goal == NutritionGoal.MAINTAIN_WEIGHT and self.goal_pace is not None:
            raise ValueError("goal_pace must be omitted when goal is maintain_weight")
        return self


class MetabolismResponse(BaseModel):
    user_id: int
    sex_for_equation: SexForEquation
    age: int
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    goal: NutritionGoal
    bmi: float
    bmi_category_general: str
    bmi_category_asian: str
    estimated_rmr_kcal_per_day: float
    activity_factor: float
    estimated_tdee_kcal_per_day: float
    goal_pace: GoalPace | None
    requested_goal_adjustment_kcal: float
    applied_goal_adjustment_kcal: float
    minimum_target_kcal: float
    target_was_safety_limited: bool
    target_kcal_per_day: float
    formula_name: str
    is_estimate: bool
    warnings: list[str]


class MealCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dish_id: int | None = Field(default=None, gt=0)
    meal_type: str = Field(min_length=1, max_length=50)
    quantity: float = Field(default=1.0, gt=0, le=100, allow_inf_nan=False)
    total_calories: float | None = Field(
        default=None,
        ge=0,
        le=20_000,
        allow_inf_nan=False,
        description="Omit to calculate from dish ingredients; provide for a manual log",
    )
    image_url: str | None = Field(default=None, max_length=2048)
    consumed_at: datetime | None = None

    @field_validator("image_url")
    @classmethod
    def empty_image_url_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def require_calorie_source(self) -> MealCreateRequest:
        if self.dish_id is None and self.total_calories is None:
            raise ValueError(
                "Provide dish_id for catalog calories or total_calories for a manual log"
            )
        return self


class MealResponse(BaseModel):
    id: int
    user_id: int
    dish_id: int | None
    dish_name: str | None
    meal_type: str
    quantity: float
    total_calories: float
    calorie_source: CalorieSource
    catalog_calories_per_serving: float | None
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
    calorie_source_counts: dict[str, int]
    meals: list[MealResponse]


def get_nutrition_tracking_repository() -> NutritionTrackingRepository:
    return NutritionTrackingRepository(get_database())


@router.post("/nutrition/calculate", response_model=MetabolismResponse)
def calculate_daily_nutrition(
    request: MetabolismRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repository: Annotated[NutritionTrackingRepository, Depends(get_nutrition_tracking_repository)],
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    try:
        result = calculate_metabolism(
            sex_for_equation=request.sex_for_equation.value,
            age=request.age,
            height_cm=request.height_cm,
            weight_kg=request.weight_kg,
            activity_level=request.activity_level.value,
            goal=request.goal.value,
            goal_pace=request.goal_pace.value if request.goal_pace else None,
            pregnant_or_breastfeeding=request.pregnant_or_breastfeeding,
            competitive_athlete=request.competitive_athlete,
            metabolism_affecting_condition=request.metabolism_affecting_condition,
        )
    except (UnsafeCalorieTargetError, UnsupportedMetabolismProfileError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "unsupported_nutrition_target", "message": str(exc)},
        ) from exc

    try:
        repository.update_metabolism_profile(
            user_id=user_id,
            sex_for_equation=request.sex_for_equation.value,
            age=request.age,
            height_cm=request.height_cm,
            weight_kg=request.weight_kg,
            activity_level=request.activity_level.value,
            goal=request.goal.value,
            bmi=result.bmi,
            tdee=result.estimated_tdee_kcal_per_day,
            target_calories=result.target_kcal_per_day,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_unavailable(exc) from exc

    return {
        "user_id": user_id,
        "sex_for_equation": request.sex_for_equation,
        "age": request.age,
        "height_cm": request.height_cm,
        "weight_kg": request.weight_kg,
        "activity_level": request.activity_level,
        "goal": request.goal,
        **_metabolism_payload(result),
    }


@router.post("/meals", response_model=MealResponse, status_code=status.HTTP_201_CREATED)
def create_meal(
    request: MealCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repository: Annotated[NutritionTrackingRepository, Depends(get_nutrition_tracking_repository)],
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
    except DishNutritionUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except MealCalorieLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _database_unavailable(exc) from exc


@router.get("/meals/daily", response_model=DailyMealsResponse)
def get_daily_meals(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repository: Annotated[NutritionTrackingRepository, Depends(get_nutrition_tracking_repository)],
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
    source_counts = {source.value: 0 for source in CalorieSource}
    for meal in meals:
        source = str(meal["calorie_source"])
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "date": day,
        "meal_count": len(meals),
        "total_calories": total,
        "target_kcal_per_day": target,
        "remaining_kcal": remaining,
        "calorie_source_counts": source_counts,
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
