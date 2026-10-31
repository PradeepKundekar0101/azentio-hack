# Claims Leakage frontend

Next.js (App Router) client for the claims-leakage app.

## Run

```bash
pnpm install
pnpm dev            # http://localhost:3000
```

The browser only talks to this app.
`/api/*` and `/health` are rewritten to the FastAPI backend at `BACKEND_URL` (default `http://127.0.0.1:8000`), so the `azentio_session` cookie is first-party.
Set it in `frontend/.env.local` if the backend runs elsewhere, then restart the dev server.
`next build` bakes the rewrite in, so set `BACKEND_URL` at build time too.
In production the App Platform ingress sends `/api` and `/health` to the backend before they reach Next.js, so the rewrite never fires there.

Sign in with the demo account configured in `backend/.env` (`DEMO_USERNAME`, `DEMO_PASSWORD`).

## Scripts

| Script | What it does |
| --- | --- |
| `pnpm dev` | Dev server |
| `pnpm build` / `pnpm start` | Production build and server |
| `pnpm lint` | ESLint |
| `pnpm typecheck` | Generates route types, then `tsc --noEmit` |
| `pnpm test` | Vitest unit tests |
| `pnpm api:types` | Regenerates `src/lib/api/schema.d.ts` from `${API_URL:-http://127.0.0.1:8000}/openapi.json` |

## Layout

- `src/app/login` - sign-in page.
- `src/app/(app)` - signed-in routes inside the app shell: Dashboard (`/`), `alerts`, `imports`, `documents`.
- `src/proxy.ts` - redirects to `/login?next=...` when there is no session cookie.
- `src/components/app-shell` - sidebar, top bar, mobile drawer, backend status and the session guard.
- `src/components/ui` - shadcn/ui components (`components.json`).
- `src/lib/api` - typed `openapi-fetch` client and `ApiError` (code, message, details).
- `src/lib/auth` - `useMe`, `useLogin`, `useLogout` and safe post-login redirects.
- `src/lib/format.ts` - rupees in Indian grouping, counts, percentages and dates.
