"""Import a sample folder (CSV files) into the configured database and process it, as a user would.

Usage: uv run python -m scripts.load_sample [--folder ../data/sample] [--database-url URL]
The fallback demo database is loaded with --database-url pointing at it.
"""

import argparse
import asyncio
from pathlib import Path

from app.core.config import REPO_ROOT, get_settings
from app.core.enums import RunScope
from app.db.session import Database
from app.ingest.service import UploadedFile, run_import
from app.pipeline import execute_run, start_run
from app.storage.spaces import Storage

DATASETS = ("policies", "policy_rules", "claims", "line_items", "settlements")


async def load(folder: Path, database_url: str | None) -> None:
    settings = get_settings()
    if database_url:
        settings = settings.model_copy(update={"database_url": type(settings.database_url)(database_url)})
    database = Database(settings)
    storage = Storage.from_settings(settings)
    files = [
        UploadedFile(f"{name}.csv", "text/csv", (folder / "csv" / f"{name}.csv").read_bytes()) for name in DATASETS
    ]
    try:
        async with database.sessionmaker() as session:
            batch = await run_import(session, storage, files, uploaded_by="load_sample")
            totals = {k: v["accepted"] + v["warnings"] for k, v in batch.counts.items()}
            print(f"Import {batch.id}: {batch.status}, accepted {totals}")
            run = await start_run(session, RunScope.BATCH, batch.id)
            run = await execute_run(session, run, settings)
            print(f"Run {run.id}: {run.status}, {run.claims_processed} claims processed, {run.claims_failed} failed")
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=REPO_ROOT / "data" / "sample")
    parser.add_argument("--database-url", default=None, help="load into this database instead of DATABASE_URL")
    args = parser.parse_args()
    asyncio.run(load(args.folder, args.database_url))


if __name__ == "__main__":
    main()
