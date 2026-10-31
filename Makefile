BACKEND := cd backend &&
PY := $(BACKEND) uv run

.PHONY: dev dev-backend dev-frontend test lint format migrate generate seed-reference reset-demo api-types openapi

dev:  ## backend :8000 and frontend :3000
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	$(PY) fastapi dev

dev-frontend:
	cd frontend && pnpm dev

test:
	$(PY) pytest -q
	cd frontend && pnpm test

lint:
	$(PY) ruff check .
	$(PY) ruff format --check .
	cd frontend && pnpm lint && pnpm typecheck

format:
	$(PY) ruff check --fix .
	$(PY) ruff format .

migrate:
	$(PY) alembic upgrade head

generate:  ## synthetic input files and invoices under data/sample/
	$(PY) python -m scripts.generate_data
	$(PY) python -m scripts.generate_invoices

seed-reference:
	$(PY) python -m scripts.seed_reference

reset-demo:  ## empties every table in the configured database, then reloads reference data
	$(PY) python -m scripts.reset_demo --yes

api-types:  ## regenerate the frontend's typed client from the running backend
	cd frontend && pnpm api:types

openapi:  ## the API contract for the investigation workspace, written to docs/openapi.json
	$(PY) python -m scripts.export_openapi
