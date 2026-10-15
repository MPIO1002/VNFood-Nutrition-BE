from __future__ import annotations

import secrets
import uuid

from fastapi.testclient import TestClient

from calcucalo.api.app import app
from calcucalo.api.auth import get_auth_service


def main() -> int:
    service = get_auth_service()
    email = f"auth-smoke-{uuid.uuid4().hex}@example.invalid"
    password = secrets.token_urlsafe(24)
    client = TestClient(app)
    try:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Auth smoke test"},
        )
        assert register.status_code == 201, register.text
        first = register.json()

        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text

        current_user = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert current_user.status_code == 200, current_user.text
        assert current_user.json()["email"] == email

        refresh = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert refresh.status_code == 200, refresh.text
        second = refresh.json()

        reused = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert reused.status_code == 401, reused.text

        logout = client.post("/api/v1/auth/logout", json={"refresh_token": second["refresh_token"]})
        assert logout.status_code == 200, logout.text
        revoked = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
        )
        assert revoked.status_code == 401, revoked.text
        print("JWT HTTP register/access/refresh/logout smoke test passed.")
        return 0
    finally:
        with service.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM app_users WHERE email = %s", (email,))


if __name__ == "__main__":
    raise SystemExit(main())
