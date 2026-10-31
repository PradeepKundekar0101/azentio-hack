# Evidence and audit trail

Level 2, point 6: every investigation keeps a complete evidence history (original calculations, detected issues, recommendations, reviewer changes, decisions, timestamps and user identity), keeps the original recommendation when an analyst overrides it, and downloads as a structured report.

## How it works

- **Investigation.** Opens the first time anyone acts on a claim: a decision on one of its alerts, an override, a note, or **Open investigation** on the evidence page. Opening freezes a full snapshot: the claim, policy terms, lines, every check result, the payable steps, duplicate decisions and each finding with its recommended correction.
- **Evidence entries** (`evidence_events`) are append-only: `opened`, `recalculated`, `decision`, `override`, `note`, `exported`. Each stores who, when, a summary and a JSON payload.
- **Tamper evidence.** Each entry's SHA-256 hash covers its own fields and the previous entry's hash. `GET` recomputes the chain and reports whether it is intact. A database trigger refuses `UPDATE` and `DELETE` on the table (`TRUNCATE`, used by demo reset and tests, still works).
- **Stable findings.** Runs delete and rebuild alerts with new IDs, so entries refer to a finding by a key (`category|rule|line|policy rule or matched claim`) and keep their own copy. Overrides carry across runs. A run that changes a claim under investigation appends a `recalculated` entry listing what moved.
- **Recommendation.** Until a dedicated corrections module exists (point 4), the recommendation is the alert's own correction: action, original amount, correction, corrected amount, calculation and policy rule (`app/evidence/recommend.py`).
- **Override.** Changes the correction applied for one finding. A reason is required, the correction cannot exceed the original amount, and the original recommendation stays in the entry and in the report.
- **Report.** `GET /api/v1/evidence/claims/{id}/report?format=pdf|json`. JSON contains every entry in full, including the frozen snapshots; the PDF is the readable version. The download itself is recorded.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/evidence` | Claims under investigation, latest activity first |
| GET | `/api/v1/evidence/claims/{claim_id}` | Findings with original and applied corrections, summary, integrity, history |
| POST | `/api/v1/evidence/claims/{claim_id}/open` | Open the investigation (idempotent) |
| POST | `/api/v1/evidence/claims/{claim_id}/overrides` | `{alert_id, correction, reason}` |
| POST | `/api/v1/evidence/claims/{claim_id}/notes` | `{text, alert_id?}` |
| GET | `/api/v1/evidence/claims/{claim_id}/report` | `?format=pdf` (default) or `json` |

`PATCH /api/v1/alerts/{id}` also writes a `decision` entry, in the same transaction as the status change.

## Code

| Path | Contents |
| --- | --- |
| `backend/app/evidence/chain.py` | Hashing and chain verification |
| `backend/app/evidence/recommend.py` | Finding key and recommendation from an alert |
| `backend/app/evidence/service.py` | Open, snapshot, decision, override, note, export, re-run capture |
| `backend/app/evidence/view.py` | The read model shared by the API and the report |
| `backend/app/evidence/report.py` | JSON and PDF report |
| `backend/app/api/evidence.py` | Routes |
| `backend/migrations/versions/2026_10_31_1615-f9a35b8bb39d_evidence_history.py` | Tables and the append-only trigger |
| `frontend/src/app/(app)/claims/[id]/evidence/` | Evidence trail page |
| `frontend/src/app/(app)/evidence/` | Evidence list (sidebar) |
| `frontend/src/lib/evidence/` | Hooks, types, helpers |

## Integrating with `feat/rbac-escalation`

This branch is cut from `main` (`928c471`) and does not know about users, roles or escalation. To bring it into the review and escalation branch:

1. **Merge** `feat/evidence-audit-trail` into `feat/rbac-escalation`. A dry run (`git merge-tree`) shows four conflicts: `backend/app/api/alerts.py` and `frontend/src/lib/api/schema.d.ts` (steps 3 and 6), plus two one-liners where both branches add something; keep both sides:
   - `backend/app/main.py`: import and include both the `users` and `evidence` routers.
   - `frontend/src/components/app-shell/nav.ts`: keep both new nav items (Evidence and the users page) and both icon imports.
2. **Migrations have two heads**: both `f9a35b8bb39d` (evidence) and the users/escalation migration revise `8b5b83935338`. Set `down_revision` in the evidence migration to the users/escalation revision (`c4d2a9e7f1b3`), then check `uv run alembic heads` shows one head.
3. **`backend/app/api/alerts.py`, `update_alert`** will conflict. Keep the review/escalation version, capture the status before changing it, and record the decision before the commit:

   ```python
   previous = alert.status          # before any field is changed
   ...                              # existing status, reviewer and escalation updates
   await evidence.record_decision(
       session, alert, principal.username, previous, note,
       actor_role=principal.role,
       extra={"escalate_to": body.escalate_to.value if body.escalate_to else None},
   )
   await session.commit()
   ```

   (`from app.evidence import service as evidence` is already imported on this branch.)
4. **Identity and role on every entry.** In `backend/app/api/evidence.py`, replace `username: CurrentUser` with `principal: CurrentPrincipal` in the four write routes and make `_actor` return `(principal.username, principal.role)`. Entries already have an `actor_role` column, and the UI shows it.
5. **Permissions (optional).** If overrides should be limited to a role, check it in `override` in `backend/app/api/evidence.py`; the service does not check roles.
6. **Frontend types.** Both branches change `frontend/src/lib/api/schema.d.ts`. Take either side, then regenerate from the merged backend (`pnpm api:types`). Decision labels already cover `evidence_requested` and `escalated` (`frontend/src/lib/evidence/model.ts`).
7. **Tests.** `backend/tests/test_evidence.py` signs in through the shared `api` fixture; if login changes, only that fixture needs updating.

On Windows, run the backend tests on top of `feat/rbac-escalation`: it carries the fix for `strftime("%-d")` in `backend/app/rules/explain.py`, without which every claim fails evaluation there.
