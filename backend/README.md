# Backend

FastAPI service managed with [uv](https://docs.astral.sh/uv/). See the [root README](../README.md) for setup and make targets.

## Layout

| Path | Contents |
| --- | --- |
| `app/main.py` | App factory, lifespan (database, storage), routers |
| `app/core/` | Settings, logging, error format, money parsing and formatting, session login, enums |
| `app/db/` | Async engine and sessions (`session.py`), every table (`models.py`) |
| `app/storage/` | DigitalOcean Spaces client |
| `app/api/` | Routes: `/health`, and `/api/v1/...` |
| `migrations/` | Alembic (async template); revision files are dated |
| `reference/` | Service codes and providers loaded by `scripts.seed_reference` |
| `scripts/` | Command-line jobs (`python -m scripts.<name>`) |

## Conventions

- Every `/api/v1` route except `auth/login` requires the session cookie.
- Errors are `{"error": {"code", "message", "details"}}`; lists take `page` and `page_size` and return `{items, total}`.
- Money is `NUMERIC(12,2)` in Postgres and `Decimal` in Python; parse input with `app.core.money.parse_amount` and format with `inr`.
- Routes get a database session with `SessionDep` and storage with `StorageDep`.
  `Storage` uses boto3, which blocks, so wrap network calls in `asyncio.to_thread` inside async routes.

## Migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```
