from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:25060/db?ssl=require
    database_url: SecretStr

    spaces_region: str
    spaces_endpoint_url: str
    spaces_bucket: str
    # Every object key is stored under this prefix, so the app never touches
    # other files in a shared bucket.
    spaces_prefix: str = ""
    spaces_access_key_id: SecretStr
    spaces_secret_access_key: SecretStr


@lru_cache
def get_settings() -> Settings:
    return Settings()
