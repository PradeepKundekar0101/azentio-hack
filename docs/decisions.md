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

## Phase 1

- **Products.** Silver: co-pay 20%, deductible ₹5,000-₹10,000, sum insured ₹3-4 lakh, room ₹3,000/day, diagnostics ₹10,000/claim, no day-care or physiotherapy cover.
  Gold: co-pay 10%, deductible ₹2,000-₹5,000, ₹5-7.5 lakh, room ₹5,000/day, diagnostics ₹15,000/claim, physiotherapy ₹20,000/period.
  Platinum: no co-pay, deductible ₹0 or ₹2,500, ₹8-10 lakh, room ₹8,000/day, diagnostics ₹25,000/claim, physiotherapy ₹30,000/period.
  Deductibles are per claim or per period; benefit periods are one year, starting between July 2025 and May 2026.
- **One value per policy rule.** The contract allows one `scope_value` per rule, so coverage needs one rule per covered claim type and per covered category.
  Policies therefore have 15-20 rules (about 5,400 in the full set) instead of the plan's 4-8.
- **Clean claims stay clear of every check.** Each policy's claims use at most 45% of its sum insured and 50% of its physiotherapy limit; room rates stay at or below 85% of the daily limit and diagnostics at or below 60% of the per-claim limit.
  Two claims of the same claimant are at least 10 days apart (incident and every service date), so they are never duplicate candidates; invoice and incident references are globally unique.
  Codes used by exclusion scenarios (cosmetic, liposuction, LASIK, IVF, vitamins) never appear in clean claims.
- **Ledger order cannot change a result.** Every policy scenario sits on a per-claim-deductible policy.
  On per-period-deductible policies settled claims come before open claims in time, so a settled claim's entitlement never depends on an open claim.
  Per-period and overall-limit scenarios get their own policies, with the breaching claim last; per-period ones have no deductible or co-pay, so "allowed in-scope amount" and "paid amount" consumption agree.
- **Policy scenarios are open claims; settled claims are clean apart from C12.** Settled claims are paid exactly their entitlement unless planted as an overpayment.
  Settled claims within the deductible have a `rejected` settlement with ₹0 approved and paid.
- **Duplicate scenarios.** The later submission is always the flagged claim.
  Exact duplicates resubmit the same invoices (reference spelled differently but equal once normalised, e.g. `INV-04521` and `inv 4521`), or 30% of the time the same incident reference, date and amount with re-issued invoice numbers.
  Lines of an exact-duplicate claim are not reported again as duplicate lines (one alert per leakage).
  Near-duplicates use one `INV-` reference with a suffixed variant (`INV-00452` and `INV452A`), 1-3 days and 1-3% apart, and score at least 0.82 under every reading of the formula (largest and smallest date gap and amount base); every other candidate pair scores below 0.79.
  Duplicate lines across claims copy one line into a follow-up visit 8-14 days later whose amount differs by at least 20%, so it can never score as a near-duplicate.
- **Legitimate repeats** are pairs of single-line claims (physiotherapy, occupational therapy, rehabilitation, dialysis, follow-up consultation, home nursing) at the same provider, within the near-duplicate window, with dissimilar invoice numbers.
  They are cleared by the repeat rule regardless of score; chemotherapy cycles (14-day minimum) never fall inside the 7-day window, so none are planted.
- **Invalid rows** are extra rows (about 2% of all rows) with exactly one problem each, so rejecting them never changes the valid data.
  Bad lines and settlements are attached to clean claims and are not counted in the requested amount; a repeated identifier is a later copy of an earlier row, and only the later copy is rejected.
  Rejected claims and one rejected policy have children, recorded as `parent_rejected`.
  Planted `requested_amount_mismatch` warnings are on otherwise clean open claims.
- **Formats.** All three exports hold the same rows in the same order (`row_index` is shared); dates and amounts vary per cell, not per file; header spellings differ per file and all compact to the importer's synonyms.
  Excel cells are text and its zip entries and document properties carry a fixed timestamp, so the same seed gives byte-identical files.
- **Verification.** `scripts/datagen/oracle.py` re-reads the CSV export, validates it, recomputes every policy check, payable ledger and duplicate rule, and must reproduce the answer key exactly; generation fails otherwise.
- **Invoices.** The 10 PDFs and 2 scans are new claims for demo-pack members (claim IDs `CLM-95xxxx`, not in the demo files); two carry a planted room-rent and exclusion finding.
  The duplicate PDF re-issues the largest settled single-invoice demo claim; `manifest.json` lists each document's expected findings as computed by the checker.

## Phase 2

- **Field contracts are declarative specs, not one Pydantic model per dataset.** `app/ingest/schemas.py` lists each field's type, pattern, choices and range; parsing collects every problem in a row at once and gives each a stable error code (`missing_field`, `negative_amount`, `ambiguous_date`, ...), which the issues table, the CSV report and the answer-key tests all use.
- **Header matching** compacts names (lowercase, letters and digits only) before the synonym lookup, so spacing, case, underscores and CamelCase never matter.
- **Ambiguous dates** are date-like values with a two-digit year (`03/04/26`); day-month order is never guessed beyond the three accepted formats.
- **Warnings, not rejections, for rule-engine findings.** A claimant who is not an insured member, a paid amount above the approved amount, and a service date more than 30 days from the incident are accepted with a warning, so the rule engine can raise them as leakage.
- **Unrecognised files or sheets** are counted under `unrecognised` (received and rejected), so reconciliation still holds and nothing disappears.
- **The import runs synchronously** (the full sample imports in about 4 seconds); processing runs are background tasks.

## Phases 3-5

- **One alert per leakage.** When several eligibility checks fail, the first carries the full requested amount and the others are recorded with ₹0, so totals never double-count. Lines of an exact-duplicate claim are not reported again as duplicate lines.
- **Settled claims raise one alert, the C12 overpayment.** Their failed policy checks are already inside the recomputed entitlement; C01-C11 results are still stored and shown on the claim page.
- **Overpayment ceiling** is the lower of the approved amount and the recomputed entitlement; the explanation names a missed deductible or co-pay when the overpayment equals it.
- **Ledger.** Settled claims consume their paid amount of the overall limit; open claims their computed payable. Per-period sub-limits and the per-period deductible consume the recomputed amounts. Claims outside the benefit period consume nothing.
- **Batch runs** reprocess every claim of the policies the batch touched, because per-period and overall limits depend on earlier claims.
- **Claimant identity for duplicates** is (policy number, claimant ID).
- **Severity** is the higher of the category's base severity and the amount band (₹50,000 critical, ₹10,000 high, ₹2,000 medium); estimated and suspected alerts stay at "review".

## Phase 7

- **Unresolved service codes are left for the reviewer** rather than classified by Claude: printed codes match exactly, otherwise a fuzzy description match (≥ 80) is proposed with its confidence.
- **Confirmed documents become one-claim import batches** (`source = document`), so they pass the identical validation path and appear in import history; the claim ID is `CLM-8` plus the document number (skipping forward past any ID an import already used).
- **The API instance is `apps-s-2vcpu-4gb`** in the deploy spec, because Docling's layout and table models need 2-3 GB while reading; its models are baked into the image.

## Brand and landing page

- **Public landing page at `/welcome`.** The dashboard stays at `/`; the proxy sends signed-out visitors at `/` to `/welcome` and every other app route to `/login`, so signed-in users never see the landing page.
- **One token file.** Colours, contrast pairs and radii moved from `globals.css` to `src/styles/theme.css`, with a theme-independent brand block for the logo, landing page and share images.
  Share images cannot read CSS variables, so `src/styles/brand.ts` mirrors the brand block and a test keeps them equal.
- **Logo.** Three ledger lines of a claim with one block fallen below the gap in the signal colour: leakage, caught and made visible. It is drawn from one geometry in `brand.ts`, on an ink tile with a hairline edge so it holds on light and dark surfaces.
- **App palette: warm paper and deep teal.** The app moved from stamp blue to the brand palette. Teal is the primary, not ember, so an action button is never mistaken for an amber warning on a screen full of alerts. Every text pair is AA in both themes; field outlines are at least 3:1.
- **Drawn backdrop instead of a photograph.** A mesh gradient (blurred colour fields), a dune and film grain in SVG: no image request, no licensing question and every colour from the tokens.
- **Geist Pixel is vendored**, one face plus its OFL licence, instead of adding the `geist` package: its latest release was newer than the lockfile's minimum release age, and only one of its faces is used.
