# Backend

FastAPI service managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `.env` with the Postgres URL and Spaces key (see [Infrastructure](#infrastructure)).

## Development

```bash
uv run alembic upgrade head
uv run fastapi dev
```

The API runs at http://127.0.0.1:8000, with interactive docs at http://127.0.0.1:8000/docs.
`GET /health` returns 200 when Postgres and Spaces are both reachable, and 503 otherwise.

## Infrastructure

All resources live in the DigitalOcean account `dev@getconch.ai`.

| Resource | Details |
| --- | --- |
| Postgres | Cluster `azentio-hack-pg` (Postgres 18, `blr1`), database `azentio`, user `azentio_app` |
| Spaces | Bucket `leaklens-files` (`sgp1`), shared with LeakLens. This app only reads and writes under `azentio-hack/`. |
| Spaces key | `azentio-hack`, limited to read/write on `leaklens-files` |

Print the database connection details:

```bash
doctl databases connection --format Host,Port $(doctl databases list --format ID,Name --no-header | awk '$2=="azentio-hack-pg"{print $1}')
```

## Using the database and Spaces in routes

```python
import asyncio

from sqlalchemy import text

from app.db import SessionDep
from app.storage import StorageDep


@app.post("/files/{name}")
async def upload(name: str, session: SessionDep, storage: StorageDep) -> dict[str, str]:
    await session.execute(text("select 1"))
    key = await asyncio.to_thread(storage.upload, name, b"...", "text/plain")
    return {"key": key, "url": storage.presigned_download_url(name)}
```

`Storage` uses boto3, which blocks, so wrap network calls in `asyncio.to_thread` inside async routes.
`presigned_download_url` only signs locally and does not need it.

## Migrations

Models subclass `app.db.Base`.
Import each models module in `migrations/env.py` so autogenerate can see it.

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

## Checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests for Postgres and Spaces run against the real DigitalOcean resources and are skipped when `.env` is missing.
