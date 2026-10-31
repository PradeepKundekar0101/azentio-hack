"""Empty every table and reload the reference data, so a demo starts from a clean upload.

Usage: uv run python -m scripts.reset_demo --yes
"""

import argparse

from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.db.models import Base
from scripts.seed_reference import seed_reference


def reset_demo(settings: Settings, *, confirm: bool) -> None:
    if not confirm:
        raise SystemExit("Refusing to empty the database without --yes.")
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with engine.begin() as connection:
            connection.execute(text(f"truncate {tables} restart identity cascade"))
    finally:
        engine.dispose()
    seed_reference(settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="confirm that every table should be emptied")
    args = parser.parse_args()
    reset_demo(get_settings(), confirm=args.yes)
    print("Database emptied and reference data reloaded.")


if __name__ == "__main__":
    main()
