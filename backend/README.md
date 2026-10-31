# Backend

FastAPI service managed with [uv](https://docs.astral.sh/uv/).

## Development

```bash
uv sync
uv run fastapi dev
```

The API runs at http://127.0.0.1:8000, with interactive docs at http://127.0.0.1:8000/docs.

## Checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
