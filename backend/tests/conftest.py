import asyncio
import os
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.main import create_app
from tests.support import migrate, truncate_all

# psycopg's async connection cannot run on Windows' default Proactor event loop, which the test
# client would otherwise create; the selector loop works on every platform.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://localhost:5432/azentio_test")
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "test-password-not-secret"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": TEST_DATABASE_URL,
        "spaces_region": "sgp1",
        "spaces_endpoint_url": "http://127.0.0.1:1",
        "spaces_bucket": "bucket",
        "spaces_prefix": "test/",
        "spaces_access_key_id": "key",
        "spaces_secret_access_key": "secret",
        "session_secret": "test-session-secret-at-least-32-characters",
        "demo_username": DEMO_USERNAME,
        "demo_password": DEMO_PASSWORD,
        "cookie_secure": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """The local test database, rebuilt from the migrations once per test session."""
    migrate(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest.fixture
def db_url(migrated_database: str) -> Iterator[str]:
    """A migrated test database with every table emptied before the test."""
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        truncate_all(connection)
    engine.dispose()
    yield migrated_database


@pytest.fixture
def settings(db_url: str) -> Settings:
    return make_settings(database_url=db_url)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    response = client.post("/api/v1/auth/login", json={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
def sql(db_url: str) -> Iterator[object]:
    """Run raw SQL against the test database: sql("select ...") -> list of rows."""
    engine = create_engine(db_url)

    def run(statement: str, **params: object) -> list:
        with engine.begin() as connection:
            result = connection.execute(text(statement), params)
            return list(result) if result.returns_rows else []

    yield run
    engine.dispose()


@pytest.fixture
def live_settings() -> Settings:
    """Settings for the real DigitalOcean resources, loaded from backend/.env."""
    get_settings.cache_clear()
    try:
        return get_settings()
    except ValidationError:
        pytest.skip("backend/.env is not configured with DigitalOcean credentials")


@pytest.fixture
def unreachable_settings() -> Settings:
    """Settings that point every dependency at a closed local port."""
    return make_settings(database_url="postgresql+psycopg://user:password@127.0.0.1:1/db")
