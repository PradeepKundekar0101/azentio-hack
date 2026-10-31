from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_ok_when_dependencies_are_reachable(
    live_settings: Settings,
) -> None:
    with TestClient(create_app(live_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "storage": "ok"},
    }


def test_health_reports_unavailable_when_dependencies_are_unreachable(
    unreachable_settings: Settings,
) -> None:
    with TestClient(create_app(unreachable_settings)) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "error", "storage": "error"},
    }
