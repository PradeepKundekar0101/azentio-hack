# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    DOCLING_ARTIFACTS_PATH=/opt/models/docling
# Docling's PDF backend needs these shared libraries.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first, so code changes reuse the cached layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Download Docling's layout and table models at build time, so the first invoice on demo day is fast.
RUN uv run --no-sync docling-tools models download -o /opt/models/docling

COPY . .
RUN uv sync --frozen --no-dev && useradd --system --uid 10001 --no-create-home app
# Code and the virtualenv stay root-owned (read-only for the app).
ENV HOME=/tmp HF_HOME=/tmp/hf
USER app
EXPOSE 8000
# Migrations and reference data run as the App Platform pre-deploy job (see infra/app-spec.yaml).
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
