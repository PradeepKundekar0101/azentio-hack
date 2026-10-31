# Decisions

Choices made where the plan (`docs/plan.md`) was ambiguous, or where the environment forced a deviation.
Each entry says what was chosen and why.

## Environment

- **Repository layout.** The plan's project folder is this repository's root: `backend/`, `frontend/`, `data/`, `docs/`.
  Phase commits are tagged `phase-0` through `phase-8`.
- **Spaces bucket in SGP1, not BLR1.** Spaces is not available in BLR1 for this account, so the app reuses the existing private bucket `leaklens-files` in Singapore (chosen by the project owner).
  Every key is written under the `azentio-hack/` prefix, and the app uses its own access key (`azentio-hack`) limited to that bucket.
  Claim documents are therefore stored outside India; revisit before handling real claims.
- **Postgres.** A dedicated cluster `azentio-hack-pg` (Postgres 18, BLR1, 1 vCPU / 1 GB).
  The app connects as `azentio_app`, which owns the `azentio` database and is not a superuser.
  It connects directly (no PgBouncer pool), so prepared statements stay enabled; pool sizes are kept small for the 1 GB node.
- **Tests use a local Postgres.** `TEST_DATABASE_URL` (default `localhost/azentio_test`) is rebuilt from the migrations at the start of each run and emptied before each test, so tests are fast and never touch the shared cluster.
  A handful of tests exercise the real DigitalOcean database and Spaces through `backend/.env`, and skip when it is missing.
- **Deployment from the public repository.** App Platform clones the public GitHub repository over HTTPS, as LeakLens does, so no GitHub app integration is needed; deploys are triggered with `doctl apps create-deployment`.

## Phase 0

- **Reference data lives in `backend/reference/`**, not under `data/`, because the deployed image contains only `backend/` and the pre-deploy job loads it.
  It has 63 service codes and 40 fictional providers.
  Repeat rules: daily room, ICU, nursing and inpatient doctor visits (1-day minimum, 7 per week); physiotherapy and dialysis (2-day minimum, 3 per week); follow-up consultations (7-day minimum, 1 per week); chemotherapy cycles (14-day minimum, 1 per week).
- **Session login.** One demo user from the environment (`DEMO_USERNAME`, `DEMO_PASSWORD`), compared in constant time.
  The cookie `azentio_session` holds a signed token (HS256, `SESSION_SECRET`, 12-hour expiry), httpOnly, `SameSite=Lax`, and `Secure` when deployed.
  There is no users table; the deployed app uses a different password and secret from local development (`.env.do`).
- **Extra traceability columns.** Every core table (policies, policy rules, claims, line items, settlements) stores `source_row` (file, sheet, row number), not only claims and line items, so alert drill-down can show the source row of any supporting record.
  `claims.incident_reference_norm` stores the normalised incident reference for duplicate checks, `validation_results.inputs` stores the inputs each check used, and `alerts.explanation` stores the plain-language text.
- **Contract enums are CHECK constraints** on text columns rather than Postgres enum types, so adding a value is a one-line migration.
- **CORS** origins come from the settings loaded at startup, so importing the app never reads configuration.
  In production the browser only talks to one domain, so CORS is a fallback for local tools.

## Brand and landing page

- **Public landing page at `/welcome`.** The dashboard stays at `/`; the proxy sends signed-out visitors at `/` to `/welcome` and every other app route to `/login`, so signed-in users never see the landing page.
- **One token file.** Colours, contrast pairs and radii moved from `globals.css` to `src/styles/theme.css`, with a theme-independent brand block for the logo, landing page and share images.
  Share images cannot read CSS variables, so `src/styles/brand.ts` mirrors the brand block and a test keeps them equal.
- **Logo.** Three ledger lines of a claim with one block fallen below the gap in the signal colour: leakage, caught and made visible. It is drawn from one geometry in `brand.ts`, on an ink tile with a hairline edge so it holds on light and dark surfaces.
- **App palette: warm paper and deep teal.** The app moved from stamp blue to the brand palette. Teal is the primary, not ember, so an action button is never mistaken for an amber warning on a screen full of alerts. Every text pair is AA in both themes; field outlines are at least 3:1.
- **Drawn backdrop instead of a photograph.** A mesh gradient (blurred colour fields), a dune and film grain in SVG: no image request, no licensing question and every colour from the tokens.
- **Geist Pixel is vendored**, one face plus its OFL licence, instead of adding the `geist` package: its latest release was newer than the lockfile's minimum release age, and only one of its faces is used.

