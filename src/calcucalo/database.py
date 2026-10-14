from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class DatabaseConfigurationError(RuntimeError):
    """Raised when PostgreSQL connection settings are missing or invalid."""


@dataclass(frozen=True)
class DatabaseSettings:
    dsn: str
    min_connections: int = 1
    max_connections: int = 5

    @classmethod
    def from_environment(cls) -> DatabaseSettings:
        dsn = os.getenv("DATABASE_URL", "").strip()
        if not dsn:
            host = os.getenv("DB_HOST", "").strip()
            port = os.getenv("DB_PORT", "5432").strip()
            database = os.getenv("DB_NAME", "").strip()
            user = os.getenv("DB_USER", "").strip()
            password = os.getenv("DB_PASSWORD", "")
            if not all((host, port, database, user, password)):
                raise DatabaseConfigurationError(
                    "Set DATABASE_URL or all of DB_HOST, DB_PORT, DB_NAME, DB_USER and DB_PASSWORD"
                )
            from urllib.parse import quote_plus

            dsn = (
                f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/"
                f"{database}?sslmode=require"
            )

        min_connections = _environment_int("DB_POOL_MIN", 1, minimum=1, maximum=20)
        max_connections = _environment_int("DB_POOL_MAX", 5, minimum=1, maximum=50)
        if max_connections < min_connections:
            raise DatabaseConfigurationError(
                "DB_POOL_MAX must be greater than or equal to DB_POOL_MIN"
            )
        return cls(
            dsn=dsn,
            min_connections=min_connections,
            max_connections=max_connections,
        )


def _environment_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise DatabaseConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise DatabaseConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


class PostgresDatabase:
    """Small thread-safe psycopg2 pool shared by API and nutrition services."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self._pool: Any | None = None
        self._pool_lock = threading.Lock()

    def _get_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is None:
                try:
                    from psycopg2.pool import ThreadedConnectionPool
                except ImportError as exc:
                    raise RuntimeError(
                        "PostgreSQL support requires psycopg2-binary. Install the API dependencies."
                    ) from exc
                self._pool = ThreadedConnectionPool(
                    self.settings.min_connections,
                    self.settings.max_connections,
                    dsn=self.settings.dsn,
                    connect_timeout=10,
                    application_name="calcucalo-api",
                )
        return self._pool

    @contextmanager
    def connection(self) -> Iterator[Any]:
        pool = self._get_pool()
        connection = pool.getconn()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            pool.putconn(connection)

    def ping(self) -> dict[str, str]:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user")
            database, user = cursor.fetchone()
        return {"database": str(database), "user": str(user)}

    def close(self) -> None:
        with self._pool_lock:
            if self._pool is not None:
                self._pool.closeall()
                self._pool = None


@lru_cache(maxsize=1)
def get_database() -> PostgresDatabase:
    return PostgresDatabase(DatabaseSettings.from_environment())


def database_is_configured() -> bool:
    return bool(
        os.getenv("DATABASE_URL")
        or all(
            os.getenv(name) for name in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
        )
    )
