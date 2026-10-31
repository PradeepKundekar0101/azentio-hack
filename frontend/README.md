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

- `src/app/welcome` - public landing page; signed-out visitors at `/` are sent here.
- `src/app/login` - sign-in page.
- `src/app/(app)` - signed-in routes inside the app shell: Dashboard (`/`), `alerts`, `imports`, `documents`.
- `src/proxy.ts` - without a session cookie, sends `/` to `/welcome` and other app routes to `/login?next=...`.
- `src/components/app-shell` - sidebar, top bar, mobile drawer, backend status and the session guard.
- `src/components/ui` - shadcn/ui components (`components.json`).
- `src/lib/api` - typed `openapi-fetch` client and `ApiError` (code, message, details).
- `src/lib/auth` - `useMe`, `useLogin`, `useLogout` and safe post-login redirects.
- `src/lib/format.ts` - rupees in Indian grouping, counts, percentages and dates.
- `src/styles` - theme tokens, brand constants, logo geometry and brand fonts (see below).

## Theme and brand

Every colour, contrast pair and radius lives in `src/styles/theme.css`; change it there and every page follows.

- `:root` and `.dark` are the app themes, read by the shadcn/ui components.
- The brand block (`--brand-*`) is the same in both themes. The logo, the landing page and the share images use it.
- `src/app/globals.css` maps the tokens to Tailwind utilities (`bg-primary`, `text-brand-signal`, `font-pixel`, ...).
- `src/styles/brand.ts` mirrors the brand block for code that cannot read CSS (share images, icons) and holds the logo (the drop leaking from a claim form) and landing-backdrop geometry.
  `brand.test.ts` fails if it drifts from `theme.css` or from `src/app/icon.svg`.
- Brand type: Geist Pixel (vendored in `src/styles/fonts`, SIL Open Font License) and Geist, loaded by `src/styles/fonts.ts` for the public pages only.
  The app keeps Atkinson Hyperlegible.

Generated assets: `src/app/opengraph-image.tsx` and `twitter-image.tsx` (1200 x 630 link preview), `apple-icon.tsx` (180 x 180) and `icon.svg`.
Share-image URLs are absolute, based on `SITE_URL` (set from App Platform's `APP_URL` in `infra/app-spec.yaml`; defaults to `http://localhost:3000`).
