# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first, so code changes reuse the cached layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && useradd --system --uid 10001 --no-create-home app
# Code and the virtualenv stay root-owned (read-only for the app).
ENV HOME=/tmp
USER app
EXPOSE 8000
# Migrations and reference data run as the App Platform pre-deploy job (see infra/app-spec.yaml).
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
