"""Load the reference service codes and providers from backend/reference/ into the database (idempotent upsert).

Usage: uv run python -m scripts.seed_reference
"""

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert

from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.db.models import Provider, ServiceCode

REFERENCE_DIR = BACKEND_ROOT / "reference"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _optional_int(value: str) -> int | None:
    return int(value) if value.strip() else None


def load_reference_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    service_codes = [
        {
            "code": row["code"],
            "description": row["description"],
            "category": row["category"],
            "repeatable": row["repeatable"].strip().lower() == "true",
            "min_interval_days": _optional_int(row["min_interval_days"]),
            "max_per_week": _optional_int(row["max_per_week"]),
        }
        for row in _read_csv(REFERENCE_DIR / "service_codes.csv")
    ]
    providers = [dict(row) for row in _read_csv(REFERENCE_DIR / "providers.csv")]
    return service_codes, providers


def seed_reference(settings: Settings) -> tuple[int, int]:
    service_codes, providers = load_reference_rows()
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with engine.begin() as connection:
            for model, rows, key in ((ServiceCode, service_codes, "code"), (Provider, providers, "provider_id")):
                statement = insert(model).values(rows)
                updates = {column: statement.excluded[column] for column in rows[0] if column != key}
                connection.execute(statement.on_conflict_do_update(index_elements=[key], set_=updates))
    finally:
        engine.dispose()
    return len(service_codes), len(providers)


def main() -> None:
    codes, providers = seed_reference(get_settings())
    print(f"Seeded {codes} service codes and {providers} providers.")


if __name__ == "__main__":
    main()
