from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Any, TypeVar

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.database import PostgresDatabase, get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


AUTH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(120),
    gender VARCHAR(50),
    age INTEGER,
    height DOUBLE PRECISION,
    weight DOUBLE PRECISION,
    activity_level VARCHAR(50),
    goal VARCHAR(50),
    bmi DOUBLE PRECISION,
    tdee DOUBLE PRECISION,
    target_calories DOUBLE PRECISION,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    replaced_by_token_id UUID REFERENCES auth_refresh_tokens(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_user_id
    ON auth_refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_expires_at
    ON auth_refresh_tokens(expires_at);
"""


class AuthError(RuntimeError):
    def __init__(self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class AuthSettings:
    secret_key: str
    algorithm: str
    issuer: str
    audience: str
    access_minutes: int
    refresh_days: int

    @classmethod
    def from_environment(cls) -> AuthSettings:
        secret = os.getenv("JWT_SECRET_KEY", "")
        if len(secret) < 32:
            raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")
        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        if algorithm not in {"HS256", "HS384", "HS512"}:
            raise RuntimeError("JWT_ALGORITHM must be HS256, HS384 or HS512")
        return cls(
            secret_key=secret,
            algorithm=algorithm,
            issuer=os.getenv("JWT_ISSUER", "calcucalo-api"),
            audience=os.getenv("JWT_AUDIENCE", "calcucalo-mobile"),
            access_minutes=_positive_environment_int("JWT_ACCESS_TOKEN_MINUTES", 15),
            refresh_days=_positive_environment_int("JWT_REFRESH_TOKEN_DAYS", 30),
        )


def _positive_environment_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.casefold()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid email address")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    message: str


class AuthService:
    def __init__(self, database: PostgresDatabase, settings: AuthSettings) -> None:
        self.database = database
        self.settings = settings
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def initialize_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self.database.connection() as connection, connection.cursor() as cursor:
                cursor.execute(AUTH_SCHEMA_SQL)
            self._schema_ready = True

    def register(self, request: RegisterRequest) -> dict[str, Any]:
        self.initialize_schema()
        password_hash = _hash_password(request.password)
        try:
            with self.database.connection() as connection, _dict_cursor(connection) as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, full_name, is_active, created_at
                    """,
                    (request.email, password_hash, request.full_name or None),
                )
                user = dict(cursor.fetchone())
                return self._issue_token_pair(cursor, user)
        except Exception as exc:
            if getattr(exc, "pgcode", None) == "23505":
                raise AuthError("Email is already registered", status.HTTP_409_CONFLICT) from exc
            raise

    def login(self, request: LoginRequest) -> dict[str, Any]:
        self.initialize_schema()
        email = request.email.casefold().strip()
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            cursor.execute(
                """
                    SELECT id, email, password_hash, full_name, is_active, created_at
                    FROM users
                    WHERE email = %s
                    """,
                (email,),
            )
            row = cursor.fetchone()
            if row is None or not _verify_password(request.password, row["password_hash"]):
                raise AuthError("Invalid email or password")
            user = dict(row)
            if not user["is_active"]:
                raise AuthError("User account is disabled", status.HTTP_403_FORBIDDEN)
            return self._issue_token_pair(cursor, user)

    def refresh(self, raw_refresh_token: str) -> dict[str, Any]:
        self.initialize_schema()
        payload = self._decode_token(raw_refresh_token, expected_type="refresh")
        token_hash = _token_hash(raw_refresh_token)
        user_id = _subject_as_int(payload)
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            cursor.execute(
                """
                    SELECT id, user_id
                    FROM auth_refresh_tokens
                    WHERE token_hash = %s
                      AND user_id = %s
                      AND revoked_at IS NULL
                      AND expires_at > NOW()
                    FOR UPDATE
                    """,
                (token_hash, user_id),
            )
            stored = cursor.fetchone()
            if stored is None or str(stored["id"]) != str(payload.get("jti")):
                raise AuthError("Refresh token is expired, revoked or unknown")

            cursor.execute(
                """
                    SELECT id, email, full_name, is_active, created_at
                    FROM users
                    WHERE id = %s
                    """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None or not row["is_active"]:
                raise AuthError("User account is unavailable")

            user = dict(row)
            tokens = self._issue_token_pair(cursor, user)
            new_refresh_payload = self._decode_token(
                tokens["refresh_token"], expected_type="refresh"
            )
            cursor.execute(
                """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = NOW(), replaced_by_token_id = %s
                    WHERE id = %s
                    """,
                (new_refresh_payload["jti"], stored["id"]),
            )
            return tokens

    def logout(self, raw_refresh_token: str) -> None:
        self.initialize_schema()
        self._decode_token(raw_refresh_token, expected_type="refresh")
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = COALESCE(revoked_at, NOW())
                    WHERE token_hash = %s
                    """,
                (_token_hash(raw_refresh_token),),
            )

    def logout_all(self, user_id: int) -> None:
        self.initialize_schema()
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    UPDATE auth_refresh_tokens
                    SET revoked_at = COALESCE(revoked_at, NOW())
                    WHERE user_id = %s AND revoked_at IS NULL
                    """,
                (user_id,),
            )

    def user_from_access_token(self, token: str) -> dict[str, Any]:
        self.initialize_schema()
        payload = self._decode_token(token, expected_type="access")
        user_id = _subject_as_int(payload)
        with self.database.connection() as connection, _dict_cursor(connection) as cursor:
            cursor.execute(
                """
                    SELECT id, email, full_name, is_active, created_at
                    FROM users
                    WHERE id = %s
                    """,
                (user_id,),
            )
            row = cursor.fetchone()
        if row is None or not row["is_active"]:
            raise AuthError("User account is unavailable")
        return dict(row)

    def _issue_token_pair(self, cursor: Any, user: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        access_expires = now + timedelta(minutes=self.settings.access_minutes)
        refresh_expires = now + timedelta(days=self.settings.refresh_days)
        access_id = str(uuid.uuid4())
        refresh_id = str(uuid.uuid4())
        common = {
            "sub": str(user["id"]),
            "iss": self.settings.issuer,
            "aud": self.settings.audience,
            "iat": now,
        }
        access_token = jwt.encode(
            {**common, "type": "access", "jti": access_id, "exp": access_expires},
            self.settings.secret_key,
            algorithm=self.settings.algorithm,
        )
        refresh_token = jwt.encode(
            {**common, "type": "refresh", "jti": refresh_id, "exp": refresh_expires},
            self.settings.secret_key,
            algorithm=self.settings.algorithm,
        )
        cursor.execute(
            """
            INSERT INTO auth_refresh_tokens (id, user_id, token_hash, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (refresh_id, user["id"], _token_hash(refresh_token), refresh_expires),
        )
        public_user = {key: user[key] for key in UserResponse.model_fields}
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.settings.access_minutes * 60,
            "refresh_expires_in": self.settings.refresh_days * 24 * 60 * 60,
            "user": public_user,
        }

    def _decode_token(self, token: str, *, expected_type: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=[self.settings.algorithm],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["sub", "type", "jti", "iat", "exp"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("Invalid token") from exc
        if payload.get("type") != expected_type:
            raise AuthError(f"Expected a {expected_type} token")
        return payload


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (TypeError, ValueError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _subject_as_int(payload: dict[str, Any]) -> int:
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("Invalid token subject") from exc


def _dict_cursor(connection: Any) -> Any:
    from psycopg2.extras import RealDictCursor

    return connection.cursor(cursor_factory=RealDictCursor)


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(get_database(), AuthSettings.from_environment())


def _as_http_error(exc: AuthError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.detail,
        headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
    )


T = TypeVar("T")


def _run_auth_action(action: Callable[[], T]) -> T:
    try:
        return action()
    except AuthError as exc:
        raise _as_http_error(exc) from exc
    except Exception as exc:
        logger.exception("Authentication database operation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from exc


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _run_auth_action(lambda: service.user_from_access_token(credentials.credentials))


@router.get("/health")
def auth_health(
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, Any]:
    def check() -> dict[str, Any]:
        service.initialize_schema()
        service.database.ping()
        return {"status": "ok", "database": "reachable"}

    return _run_auth_action(check)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, Any]:
    return _run_auth_action(lambda: service.register(request))


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, Any]:
    return _run_auth_action(lambda: service.login(request))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, Any]:
    return _run_auth_action(lambda: service.refresh(request.refresh_token))


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: RefreshRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    _run_auth_action(lambda: service.logout(request.refresh_token))
    return {"message": "Logged out"}


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    _run_auth_action(lambda: service.logout_all(int(current_user["id"])))
    return {"message": "Logged out from all devices"}


@router.get("/me", response_model=UserResponse)
def me(
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    return current_user
