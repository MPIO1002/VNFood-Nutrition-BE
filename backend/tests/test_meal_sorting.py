from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any, Self

from calcucalo.repositories.diary import DiaryRepository
from calcucalo.repositories.nutrition_tracking import NutritionTrackingRepository


class FakeCursor:
    def __init__(self, queries: list[str]) -> None:
        self.queries = queries

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(
        self, query: str, _params: tuple[Any, ...] | None = None
    ) -> None:
        self.queries.append(query)

    def fetchall(self) -> list[dict[str, Any]]:
        return []

    def fetchone(self) -> dict[str, Any]:
        return {"target_calories": None, "goal": None}


class FakeConnection:
    def __init__(self, queries: list[str]) -> None:
        self.queries = queries

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self, **_kwargs: Any) -> FakeCursor:
        return FakeCursor(self.queries)


class FakeDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []

    @contextmanager
    def connection(self) -> Iterator[FakeConnection]:
        yield FakeConnection(self.queries)


def _assert_meal_type_priority(query: str) -> None:
    normalized = " ".join(query.lower().split())
    ranks = re.findall(
        r"when '(breakfast|lunch|dinner|snack)' then (\d+)", normalized
    )
    assert ranks == [
        ("breakfast", "1"),
        ("lunch", "2"),
        ("snack", "3"),
        ("dinner", "4"),
    ]
    assert "end desc" in normalized


def test_diary_image_selection_prefers_later_meal_type() -> None:
    database = FakeDatabase()
    repository = DiaryRepository(database)

    repository._fetch_daily_data(
        user_id=7,
        start_date=date(2026, 10, 21),
        end_date_excl=date(2026, 10, 22),
    )

    _assert_meal_type_priority(database.queries[0])
    assert "consumed_at desc" in " ".join(database.queries[0].lower().split())


def test_daily_meals_are_ordered_by_meal_type_then_consumed_at() -> None:
    database = FakeDatabase()
    repository = NutritionTrackingRepository(database)

    repository.daily_meals(user_id=7, day=date(2026, 10, 21))

    query = database.queries[-1]
    _assert_meal_type_priority(query)
    normalized = " ".join(query.lower().split())
    assert "ml.consumed_at asc" in normalized
    assert "ml.id asc" in normalized
