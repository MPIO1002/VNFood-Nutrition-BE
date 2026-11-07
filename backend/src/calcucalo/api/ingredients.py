"""Ingredients search API.

GET /api/v1/ingredients/search
    Search ingredients by name (Vietnamese food database).
    Returns id, name, calories per 100g, protein, fat, carb.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..core.database import get_database
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ingredients", tags=["ingredients"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class IngredientItem(BaseModel):
    id: int
    name: str
    calories_per_100g: float
    protein_g: float
    fat_g: float
    carb_g: float


class IngredientSearchResponse(BaseModel):
    query: str
    total: int
    results: list[IngredientItem]


# ---------------------------------------------------------------------------
# Repository helper (inline — simple enough to not warrant a separate file)
# ---------------------------------------------------------------------------


def _search_ingredients(
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Full-text iLIKE search on ingredients_name in the ingredients table."""
    db = get_database()
    pattern = f"%{query}%"
    with db.connection() as conn:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Count total matches
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM   ingredients
                WHERE  ingredients_name ILIKE %s
                """,
                (pattern,),
            )
            total = int((cur.fetchone() or {}).get("total", 0))

            # Fetch page
            cur.execute(
                """
                SELECT
                    id,
                    ingredients_name AS name,
                    calories          AS calories_per_100g,
                    protein           AS protein_g,
                    fat               AS fat_g,
                    carb              AS carb_g
                FROM   ingredients
                WHERE  ingredients_name ILIKE %s
                ORDER  BY ingredients_name
                LIMIT  %s OFFSET %s
                """,
                (pattern, limit, offset),
            )
            rows = cur.fetchall()

    return {
        "total": total,
        "results": [
            {
                "id":                 int(r["id"]),
                "name":               r["name"],
                "calories_per_100g":  float(r["calories_per_100g"]),
                "protein_g":          float(r["protein_g"]),
                "fat_g":              float(r["fat_g"]),
                "carb_g":             float(r["carb_g"]),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/v1/ingredients/search
# ---------------------------------------------------------------------------


@router.get(
    "/search",
    response_model=IngredientSearchResponse,
    summary="Tìm kiếm thành phần dinh dưỡng theo tên",
    description=(
        "Tìm kiếm trong bảng nguyên liệu (ingredients) của cơ sở dữ liệu thực phẩm Việt Nam. "
        "Tìm kiếm theo chuỗi con không phân biệt hoa thường (ILIKE). "
        "Trả về id, tên, và thành phần dinh dưỡng per 100g. "
        "Dùng để hỗ trợ autocomplete khi người dùng xác định thành phần món ăn."
    ),
)
def search_ingredients(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=200,
            description="Từ khóa tìm kiếm tên thành phần, ví dụ: 'gà', 'bò', 'rau muống'",
        ),
    ],
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Số kết quả tối đa (mặc định 20)"),
    ] = 20,
    offset: Annotated[
        int,
        Query(ge=0, description="Bỏ qua N kết quả đầu để phân trang (mặc định 0)"),
    ] = 0,
) -> dict[str, Any]:
    try:
        result = _search_ingredients(q.strip(), limit=limit, offset=offset)
    except Exception as exc:
        logger.error("Ingredients search error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingredient search service temporarily unavailable",
        ) from exc

    return {
        "query":   q.strip(),
        "total":   result["total"],
        "results": result["results"],
    }

