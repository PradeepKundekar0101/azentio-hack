"""Application settings, read only from environment variables (and the gitignored backend/.env)."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
DATA_DIR = REPO_ROOT / "data"
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "demo"] = "local"
    app_version: str = "0.1.0"

    # SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:25060/db?sslmode=require
    database_url: SecretStr
    # "transaction" when connecting through DO's PgBouncer pool, which cannot use prepared statements.
    db_pool_mode: Literal["session", "transaction"] = "session"
    # Small defaults: a 1 GB managed Postgres node has about 22 connection slots for every process.
    db_pool_size: int = 5
    db_max_overflow: int = 5

    spaces_region: str
    spaces_endpoint_url: str
    spaces_bucket: str
    # Every object key is stored under this prefix, so the app never touches other files in a shared bucket.
    spaces_prefix: str = ""
    spaces_access_key_id: SecretStr
    spaces_secret_access_key: SecretStr
    # Local development only: keep files in this directory instead of Spaces.
    local_storage_dir: str | None = None

    # Shared demo login, kept in an httpOnly cookie holding a signed session token.
    session_secret: SecretStr = Field(min_length=32)
    session_max_age_minutes: int = 12 * 60
    cookie_secure: bool = True
    demo_username: str = "demo"
    demo_password: SecretStr

    # Deductible and co-pay are normal policy application; set true to raise alerts for them on open claims too.
    alert_on_adjustments: bool = False
    near_duplicate_threshold: Decimal = Decimal("0.80")
    # Severity thresholds on calculated amounts (rupees).
    severity_critical_amount: Decimal = Decimal("50000")
    severity_high_amount: Decimal = Decimal("10000")
    severity_medium_amount: Decimal = Decimal("2000")

    # Claude reads uploaded invoices (structured extraction, and vision for scanned pages). Unset: reading is off.
    anthropic_api_key: SecretStr | None = None
    extraction_model: str = "claude-haiku-5-5"

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
