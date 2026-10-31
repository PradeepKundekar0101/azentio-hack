# azentio-hack

| Directory | Stack |
| --- | --- |
| [`frontend/`](frontend) | Next.js (App Router, TypeScript, Tailwind CSS, ESLint), managed with pnpm |
| [`backend/`](backend) | FastAPI (Python 3.13), managed with uv |

## Run locally

```bash
pnpm --dir frontend install
pnpm --dir frontend dev
```

```bash
uv run --directory backend fastapi dev
```

The frontend runs at http://localhost:3000 and the backend at http://127.0.0.1:8000 (API docs at `/docs`).
