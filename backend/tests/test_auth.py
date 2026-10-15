from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from calcucalo.api.app import app
from calcucalo.api.auth import (
    AuthError,
    AuthService,
    AuthSettings,
    RegisterRequest,
    _hash_password,
    _verify_password,
)


class RecordingCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, parameters: tuple[Any, ...]) -> None:
        self.executions.append((query, parameters))


def settings() -> AuthSettings:
    return AuthSettings(
        secret_key="test-secret-key-with-more-than-thirty-two-characters",
        algorithm="HS256",
        issuer="test-issuer",
        audience="test-audience",
        access_minutes=15,
        refresh_days=30,
    )


def test_password_is_hashed_and_verified() -> None:
    password_hash = _hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert _verify_password("correct horse battery staple", password_hash)
    assert not _verify_password("wrong password", password_hash)


def test_token_pair_has_distinct_typed_tokens_and_stores_only_hash() -> None:
    service = AuthService(database=None, settings=settings())  # type: ignore[arg-type]
    cursor = RecordingCursor()
    user = {
        "id": 7,
        "email": "user@example.com",
        "full_name": "Test User",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    pair = service._issue_token_pair(cursor, user)
    access = service._decode_token(pair["access_token"], expected_type="access")
    refresh = service._decode_token(pair["refresh_token"], expected_type="refresh")

    assert access["sub"] == "7"
    assert refresh["sub"] == "7"
    assert access["jti"] != refresh["jti"]
    assert pair["refresh_token"] not in cursor.executions[0][1]
    assert len(cursor.executions[0][1][2]) == 64
    with pytest.raises(AuthError):
        service._decode_token(pair["access_token"], expected_type="refresh")


def test_register_request_normalizes_email_and_limits_bcrypt_input() -> None:
    request = RegisterRequest(email="  USER@Example.COM ", password="strong-password")
    assert request.email == "user@example.com"

    with pytest.raises(ValueError):
        RegisterRequest(email="not-an-email", password="strong-password")
    with pytest.raises(ValueError):
        RegisterRequest(email="user@example.com", password="á" * 40)


def test_auth_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/auth/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
        "/api/v1/auth/me",
    } <= paths
