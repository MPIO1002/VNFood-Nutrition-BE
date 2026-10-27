"""API routes for:

1. Image upload → Cloudinary URL  (POST /api/v1/upload/image)
2. User profile read/update       (GET/PATCH /api/v1/profile)
3. Weight update                  (POST /api/v1/profile/weight)
4. Weight history                 (GET /api/v1/profile/weight/history)
5. Progress stats (weekly)        (GET /api/v1/progress/weekly)
6. Progress stats (monthly)       (GET /api/v1/progress/monthly)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.database import get_database
from ..repositories.user_profile import UserNotFoundError, UserProfileRepository
from ..services.cloudinary_upload import (
    CloudinaryConfigError,
    CloudinaryUploadError,
    cloudinary_is_configured,
    upload_image,
)
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["profile and progress"])

BANGKOK_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")

# ---------------------------------------------------------------------------
# Allowed image MIME types and max size
# ---------------------------------------------------------------------------
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/heic",
    "image/heif",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ImageUploadResponse(BaseModel):
    url: str
    filename: str
    size_bytes: int
    content_type: str


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = Field(default=None, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=2048)

    @field_validator("full_name")
    @classmethod
    def non_empty_name(cls, value: str | None) -> str | None:
        if value is not None and len(value.strip()) == 0:
            raise ValueError("full_name must not be blank")
        return value


class ProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    avatar_url: str | None
    gender: str | None
    sex_for_equation: str | None
    age: int | None
    height: float | None
    weight: float | None
    activity_level: str | None
    goal: str | None
    bmi: float | None
    tdee: float | None
    target_calories: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WeightUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weight_kg: float = Field(gt=0, le=700, allow_inf_nan=False,
                             description="New body weight in kilograms")
    recorded_at: datetime | None = Field(
        default=None,
        description="When this measurement was taken (ISO-8601); defaults to now (UTC+7)"
    )
    note: str | None = Field(default=None, max_length=500)


class WeightLogResponse(BaseModel):
    id: int
    user_id: int
    weight_kg: float
    recorded_at: datetime
    note: str | None


class WeeklyStatItem(BaseModel):
    week_label: str
    week_start: str
    week_end: str
    meal_count: int
    days_logged: int
    total_calories: float
    avg_daily_calories: float
    target_weekly_kcal: float | None
    adherence_pct: float | None
    total_protein_g: float
    total_fat_g: float
    total_carb_g: float


class WeeklyStatsResponse(BaseModel):
    user_id: int
    weeks: int
    data: list[WeeklyStatItem]


class MonthlyStatItem(BaseModel):
    month_label: str
    month_start: str
    days_in_month: int
    meal_count: int
    days_logged: int
    total_calories: float
    avg_daily_calories: float
    target_monthly_kcal: float | None
    adherence_pct: float | None
    total_protein_g: float
    total_fat_g: float
    total_carb_g: float


class MonthlyStatsResponse(BaseModel):
    user_id: int
    months: int
    data: list[MonthlyStatItem]


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_profile_repo() -> UserProfileRepository:
    return UserProfileRepository(get_database())


# ---------------------------------------------------------------------------
# 1. Image upload endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/upload/image",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image to Cloudinary",
    description=(
        "Accepts a multipart image file (JPEG, PNG, WebP, GIF, HEIC/HEIF; max 10 MB). "
        "Returns a Cloudinary secure URL that can be stored in meal logs or profile avatar. "
        "Requires CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET in the "
        "server environment."
    ),
)
async def upload_image_endpoint(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    image: Annotated[UploadFile, File(description="Image file to upload")],
) -> dict[str, Any]:
    if not cloudinary_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Image upload service is not configured. "
                "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET."
            ),
        )

    content_type = (image.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{content_type}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Uploaded file is empty")
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {MAX_IMAGE_BYTES // 1024 // 1024} MB limit",
        )

    filename = image.filename or "upload.jpg"
    try:
        url = upload_image(payload, filename=filename)
    except CloudinaryConfigError as exc:
        logger.error("Cloudinary config error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except CloudinaryUploadError as exc:
        logger.error("Cloudinary upload error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return {
        "url": url,
        "filename": filename,
        "size_bytes": len(payload),
        "content_type": content_type,
    }


# ---------------------------------------------------------------------------
# 2. Profile – read
# ---------------------------------------------------------------------------


@router.get(
    "/profile",
    response_model=ProfileResponse,
    summary="Get current user profile",
)
def get_profile(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[UserProfileRepository, Depends(get_profile_repo)],
) -> dict[str, Any]:
    try:
        return repo.get_profile(int(current_user["id"]))
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# 3. Profile – update (name / avatar)
# ---------------------------------------------------------------------------


@router.patch(
    "/profile",
    response_model=ProfileResponse,
    summary="Update profile (full_name and/or avatar_url)",
    description=(
        "Partially update the authenticated user's display name or avatar URL. "
        "To set the avatar after uploading via POST /upload/image, pass the returned URL here."
    ),
)
def update_profile(
    request: ProfileUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[UserProfileRepository, Depends(get_profile_repo)],
) -> dict[str, Any]:
    try:
        return repo.update_profile(
            int(current_user["id"]),
            full_name=request.full_name,
            avatar_url=request.avatar_url,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# 4. Weight – update (new measurement)
# ---------------------------------------------------------------------------


@router.post(
    "/profile/weight",
    response_model=WeightLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a new body weight measurement",
    description=(
        "Records the user's current weight in the weight_logs table and updates "
        "the weight field on the users profile. The latest measurement is always "
        "reflected in GET /profile."
    ),
)
def add_weight(
    request: WeightUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[UserProfileRepository, Depends(get_profile_repo)],
) -> dict[str, Any]:
    recorded_at = request.recorded_at
    if recorded_at is not None and recorded_at.tzinfo is not None:
        recorded_at = recorded_at.astimezone(BANGKOK_TIMEZONE).replace(tzinfo=None)
    try:
        return repo.add_weight_log(
            int(current_user["id"]),
            weight_kg=request.weight_kg,
            recorded_at=recorded_at,
            note=request.note,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# 5. Weight – history
# ---------------------------------------------------------------------------


@router.get(
    "/profile/weight/history",
    response_model=list[WeightLogResponse],
    summary="Get weight log history",
)
def weight_history(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[UserProfileRepository, Depends(get_profile_repo)],
    limit: Annotated[int, Query(ge=1, le=200, description="Number of entries to return")] = 30,
) -> list[dict[str, Any]]:
    try:
        return repo.get_weight_history(int(current_user["id"]), limit=limit)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# 6. Progress stats – weekly
# ---------------------------------------------------------------------------


@router.get(
    "/progress/weekly",
    response_model=WeeklyStatsResponse,
    summary="Weekly calorie and macro progress stats",
    description=(
        "Aggregate meal_logs into weekly buckets. Returns up to 52 weeks. "
        "Each bucket includes total/average calories, macro totals, days logged, "
        "and adherence percentage vs. the user's saved calorie target."
    ),
)
def weekly_progress(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[UserProfileRepository, Depends(get_profile_repo)],
    weeks: Annotated[int, Query(ge=1, le=52, description="Number of weeks to include")] = 4,
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    today = datetime.now(BANGKOK_TIMEZONE).date()
    try:
        data = repo.weekly_stats(user_id, weeks=weeks, reference_date=today)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _db_error(exc) from exc
    return {"user_id": user_id, "weeks": weeks, "data": data}


# ---------------------------------------------------------------------------
# 7. Progress stats – monthly
# ---------------------------------------------------------------------------


@router.get(
    "/progress/monthly",
    response_model=MonthlyStatsResponse,
    summary="Monthly calorie and macro progress stats",
    description=(
        "Aggregate meal_logs into monthly buckets. Returns up to 24 months. "
        "Each bucket includes total/average calories, macro totals, days logged, "
        "and adherence percentage vs. the user's saved calorie target."
    ),
)
def monthly_progress(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    repo: Annotated[UserProfileRepository, Depends(get_profile_repo)],
    months: Annotated[int, Query(ge=1, le=24, description="Number of months to include")] = 3,
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    today = datetime.now(BANGKOK_TIMEZONE).date()
    try:
        data = repo.monthly_stats(user_id, months=months, reference_date=today)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise _db_error(exc) from exc
    return {"user_id": user_id, "months": months, "data": data}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _db_error(exc: Exception) -> HTTPException:
    logger.error("Profile/progress DB error", exc_info=(type(exc), exc, exc.__traceback__))
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Profile service is temporarily unavailable",
    )
