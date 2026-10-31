# Evidence and audit trail

Level 2, point 6: every investigation keeps a complete evidence history (original calculations, detected issues, recommendations, reviewer changes, decisions, timestamps and user identity), keeps the original recommendation when an analyst overrides it, and downloads as a structured report.

## How it works

- **Investigation.** Opens the first time anyone acts on a claim: a decision on one of its alerts, an override, a note, or **Open investigation** on the evidence page. Opening freezes a full snapshot: the claim, policy terms, lines, every check result, the payable steps, duplicate decisions and each finding with its recommended correction.
- **Evidence entries** (`evidence_events`) are append-only: `opened`, `recalculated`, `decision`, `override`, `note`, `exported`. Each stores who, when, a summary and a JSON payload.
- **Tamper evidence.** Each entry's SHA-256 hash covers its own fields and the previous entry's hash. `GET` recomputes the chain and reports whether it is intact. A database trigger refuses `UPDATE` and `DELETE` on the table (`TRUNCATE`, used by demo reset and tests, still works).
- **Stable findings.** Runs delete and rebuild alerts with new row IDs, so entries refer to a finding by its stable finding ID (`ALR-...`) and keep their own copy. Overrides carry across runs. A run that changes a claim under investigation appends a `recalculated` entry listing what moved.
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

## Integration with users, roles and escalation

Merged into `sharon/main` together with `feat/rbac-escalation` (31 Oct 2026):

- Every evidence entry records the signed-in principal's username and role (`actor_role`), and `PATCH /api/v1/alerts/{id}` writes a `decision` entry in the same transaction as the status change, carrying the role and, for escalations, the target (`extra.escalate_to`).
- The migrations form one chain: `e5abd29e0ea8` (graph) → `f9a35b8bb39d` (evidence) → `c4d2a9e7f1b3` (users and escalation).
- Overrides are open to every role; limiting them is a one-line check in the `override` route if the team wants it.

### Contract with `docs/plan-investigation.md`

- Findings are keyed by the alert's stable finding ID (`ALR-...`), so decisions and evidence entries refer to the same IDs as the rest of the investigation work.
- `analysis_events` for the claim (system and AI steps) appear on the evidence page under "Analysis steps" and in the JSON report, next to the analysts' entries. They are not part of the hash chain.
- When the corrections module (Phase E, `corrections` with `COR-...` IDs) lands, `app/evidence/recommend.py` is the one place to switch the recommendation source from the alert to the correction set.
- On Windows, `main`'s `backend/app/rules/explain.py` still uses `strftime("%-d")`, which raises; `feat/rbac-escalation` carries the fix.
