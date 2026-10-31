from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.db import SessionDep
from app.main import create_app


def test_session_connects_as_app_user_to_app_database(
    live_settings: Settings,
) -> None:
    app = create_app(live_settings)

    @app.get("/_test/whoami")
    async def whoami(session: SessionDep) -> dict[str, str]:
        result = await session.execute(text("select current_user, current_database()"))
        user, database = result.one()
        return {"user": user, "database": database}

    with TestClient(app) as client:
        response = client.get("/_test/whoami")

    assert response.status_code == 200
    assert response.json() == {"user": "azentio_app", "database": "azentio"}
