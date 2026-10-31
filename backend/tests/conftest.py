import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


@pytest.fixture
def live_settings() -> Settings:
    """Settings for the real DigitalOcean resources, loaded from backend/.env."""
    try:
        return get_settings()
    except ValidationError:
        pytest.skip("backend/.env is not configured with DigitalOcean credentials")


@pytest.fixture
def unreachable_settings() -> Settings:
    """Settings that point every dependency at a closed local port."""
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:password@127.0.0.1:1/db",
        spaces_region="sgp1",
        spaces_endpoint_url="http://127.0.0.1:1",
        spaces_bucket="bucket",
        spaces_prefix="test/",
        spaces_access_key_id="key",
        spaces_secret_access_key="secret",
    )
