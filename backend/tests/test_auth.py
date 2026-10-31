from fastapi.testclient import TestClient

from app.core.security import COOKIE_NAME
from tests.conftest import DEMO_PASSWORD, DEMO_USERNAME


def test_login_sets_http_only_session_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"username": DEMO_USERNAME}
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_me_returns_the_logged_in_user(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json() == {"username": DEMO_USERNAME}


def test_wrong_password_is_rejected_without_a_cookie(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": "wrong"})

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "invalid_credentials", "message": "Invalid username or password", "details": None}
    }
    assert "set-cookie" not in response.headers


def test_api_routes_require_a_session(client: TestClient) -> None:
    response = client.get("/api/v1/reference/providers")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_tampered_session_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, "not-a-valid-token")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_logout_clears_the_session(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert auth_client.get("/api/v1/auth/me").status_code == 401


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/health")

    # Spaces points at a closed port in tests, so the check fails, but it must not ask for a login.
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "ok"
