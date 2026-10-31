# Claims Leakage

Ingests claims and policy data, validates every claim against its policy rules, detects duplicates, calculates leakage, and explains every alert in a dashboard.

All validation and money calculations are deterministic Python, traceable to a stored rule and record.
AI is used only to read uploaded documents, behind the same validation as file imports.

The build follows [docs/plan.md](docs/plan.md) phase by phase; judgement calls are recorded in [docs/decisions.md](docs/decisions.md).

| Directory | Contents |
| --- | --- |
| [`backend/`](backend) | FastAPI, SQLAlchemy 2 (async, psycopg 3), Alembic; Python 3.12 managed with uv |
| [`frontend/`](frontend) | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, TanStack Query; pnpm |
| [`infra/`](infra) | DigitalOcean App Platform spec and renderer |
| [`docs/`](docs) | Plan and decisions |

## Infrastructure

All resources live in the DigitalOcean account `dev@getconch.ai`.

| Resource | Details |
| --- | --- |
| Postgres | Cluster `azentio-hack-pg` (Postgres 18, `blr1`), database `azentio`, user `azentio_app` (not a superuser) |
| Spaces | Bucket `leaklens-files` (`sgp1`, private), shared with LeakLens; this app only uses keys under `azentio-hack/` |
| Spaces key | `azentio-hack`, limited to read/write on `leaklens-files` |

## Local setup

Requirements: Python 3.12 with `uv`, Node 22+ with `pnpm`, and a local Postgres for tests (`createdb azentio_test`).

```bash
cp backend/.env.example backend/.env   # fill in the database URL, Spaces key, session secret and demo login
cd backend && uv sync && cd ../frontend && pnpm install && cd ..
make migrate seed-reference
make dev                               # backend :8000, frontend :3000
```

Log in with `DEMO_USERNAME` / `DEMO_PASSWORD` from `backend/.env`.

## Make targets

| Target | What it does |
| --- | --- |
| `make dev` | Backend on :8000 and frontend on :3000 |
| `make test` | Backend pytest and frontend vitest |
| `make lint` | ruff, ESLint and TypeScript checks |
| `make migrate` | Alembic migrations against `DATABASE_URL` |
| `make seed-reference` | Load service codes and providers from `backend/reference/` (idempotent) |
| `make generate` | Synthetic input files and invoices under `data/sample/` |
| `make reset-demo` | Empty every table in the configured database, then reload reference data |
| `make api-types` | Regenerate the frontend's typed API client from the running backend |

## Tests

Backend tests run against a local Postgres database (`TEST_DATABASE_URL`, default `postgresql+psycopg://localhost:5432/azentio_test`), rebuilt from the migrations at the start of each run.
A few tests use the real DigitalOcean database and Spaces through `backend/.env`, and are skipped when it is missing.

## Deployment

The app runs on DigitalOcean App Platform (`infra/app-spec.yaml`): `api` (the backend Docker image) and `web` (Next.js) on one domain, with a pre-deploy job that runs migrations and loads reference data.
Secrets come from `backend/.env` and the deployment-only `.env.do` (both gitignored) through `infra/render_spec.py`; the deployed demo login is different from the local one.

```bash
python3 infra/render_spec.py > "$TMPDIR/spec.yaml" && doctl apps create --spec "$TMPDIR/spec.yaml"
```
