# Claims Leakage: Cross-claim Correlation, Document Analysis and Settlement Corrections

Working copy of the implementation plan for capabilities 1 (cross-claim correlation), 2 (document and invoice analysis) and 4 (settlement corrections), built on top of the existing app described in `docs/plan.md`.
It also defines the contract that a teammate's investigation workspace, analyst decisions and audit trail (capabilities 3, 5 and 6) build on.
Judgement calls made while building it are recorded in `docs/decisions.md`.

## Scope

| Capability | What this plan delivers |
| --- | --- |
| 1. Cross-claim correlation | A relationship graph over claims, policies, claimants, providers, invoices, incidents and documents; related-claim groups with the matching attributes that connect them; a reusable graph component |
| 2. Document and invoice analysis | Extraction from invoices and discharge summaries (repair estimates as a stretch) with a source reference on every value; comparison against the claim record; discrepancies with both values and their sources |
| 4. Settlement corrections | Specific, sequenced corrections per claim, each with original amount, corrected amount, calculation and supporting policy rule or evidence; a recommended settlement that reconciles exactly |

Out of scope (teammate): the investigation workspace UI (3), analyst decisions and escalation (5), audit trail, user identity and the downloadable report (6), and all role-based access.
This plan provides the data, IDs, immutability and events those features need (see *Integration contract*).

## Rules for the coding agent

1. Work phase by phase; each phase ends with passing acceptance criteria and a tagged commit.
2. Do not modify existing behaviour except where a phase says so.
   All existing tests must keep passing.
3. Analysis outputs are append-only: never update or delete an extraction, discrepancy, relationship group or correction.
   A new run creates a new version.
4. Code calculates money and matches records.
   The LLM extracts text into schemas and suggests matches; every AI output is labelled `generated_by = ai`, stores the model and prompt version, and is verified against the source before use.
5. Every endpoint depends on `get_current_user()`.
   For now it returns the demo user; the teammate replaces it with real authentication.
6. Money in `Decimal` / `NUMERIC(12,2)`.
   Verify library APIs against current documentation.

## Architecture additions

Three new pipeline stages run after the existing stages, and each writes versioned results that the teammate's workspace reads.

1. Existing: ingest → rules → duplicates → alerts (unchanged).
2. Documents (Tasks 3, 4): when a claim has documents, extract them, then compare the extraction with the claim record and store discrepancies.
3. Correlation (Task 2): rebuild graph nodes and edges for the claims in scope, recompute related-claim groups, and raise cross-claim alerts.
4. Corrections (Task 5): build a new correction set for each affected claim from rule results, duplicate matches and document discrepancies.
5. Each stage writes a row to `analysis_events`, which the teammate's audit trail consumes.

Stages run in this order inside the processing run, and can also be triggered per claim.

New backend modules:

```
backend/app/
  graph/        nodes.py edges.py groups.py alerts.py
  documents/    classify.py schemas.py extract.py provenance.py compare.py matching.py
  corrections/  builder.py types.py
  events.py     analysis_events writer
  api/          graph.py documents_v2.py corrections.py investigation.py
```

New frontend pieces, built as reusable components so the teammate's workspace can embed them:

- `RelatedClaimsGraph`: React Flow graph of a claim's related group; clicking a node or edge shows its records and evidence.
- `DocumentComparison`: claim values and document values side by side, discrepancies highlighted, with a PDF viewer jumping to the page and box of the selected value.
- `CorrectionsTable`: ordered corrections with original, corrected, difference, calculation and rule; totals that reconcile.
- A simple demo page per claim until the teammate's workspace exists.

New dependencies: networkx, scipy (`linear_sum_assignment`), rapidfuzz (already used), React Flow, react-pdf.

## New database tables

All new analysis tables are append-only and versioned; the latest result is the highest version, and older versions stay available for the audit trail.

Finding ID format (shared with the teammate): every reviewable item has a stable string ID with a type prefix: `ALR-…` (alert), `DSC-…` (document discrepancy), `REL-…` (relationship group), `COR-…` (correction).
Decisions in the teammate's tables reference these IDs.

Correlation graph:

| Table | Key columns |
| --- | --- |
| `graph_nodes` | node_id, node_type (claim / policy / claimant / provider / invoice / incident / document), node_key, label, attributes (jsonb) |
| `graph_edges` | edge_id, build_id, from_node, to_node, edge_type, strength (structural / strong / weak), evidence (jsonb: matched fields and values, source records), score |
| `relationship_groups` | group_id (`REL-…`), build_id, version, claim_ids (text[]), policy_count, tags (text[]), total_requested, summary, created_at |
| `graph_builds` | build_id, started_at, finished_at, scope, node_count, edge_count, group_count, config (jsonb) |

Documents:

| Table | Key columns |
| --- | --- |
| `documents` (extended) | add claim_id (required for new uploads), doc_type, page_count, phash |
| `document_extractions` | extraction_id, document_id, version, doc_type, schema_version, model, prompt_version, status (ok / needs_review / failed), validation_errors (jsonb), created_at |
| `extracted_fields` | extraction_id, field_path (e.g. `header.invoice_number`, `lines[3].amount`), value_text, value_normalised, page, bbox (jsonb), source_quote, provenance_status (verified / unverified / page_only), confidence |
| `extracted_lines` | extraction_id, line_no, description, service_code, service_date, quantity, unit_price, amount, page, bbox |
| `document_comparisons` | comparison_id, claim_id, extraction_id, version, line_matches (jsonb), created_at |
| `document_discrepancies` | discrepancy_id (`DSC-…`), comparison_id, claim_id, type, severity, claim_value, document_value, difference, amount_impact, amount_type (calculated / estimated / suspected), claim_ref (jsonb), document_ref (jsonb: document, page, bbox, quote), generated_by (rule / ai), explanation |

Corrections:

| Table | Key columns |
| --- | --- |
| `correction_sets` | set_id, claim_id, version, requested_amount, recommended_payable, total_reduction, paid_amount (settled claims), recovery_amount, inputs_hash, created_at |
| `corrections` | correction_id (`COR-…`), set_id, claim_id, line_id (nullable), sequence, type, original_amount, corrected_amount, difference, calculation_text, calculation (jsonb: formula and inputs), policy_rule_id, evidence_refs (text[] of finding IDs), amount_type, confidence, generated_by, explanation, applied (bool) |

Events:

| Table | Key columns |
| --- | --- |
| `analysis_events` | event_id, event_type, claim_id, entity_type, entity_id, actor_type (system / ai), model, prompt_version, payload (jsonb), created_at |

Event types: `extraction_created`, `comparison_created`, `graph_built`, `group_created`, `correction_set_created`, `cross_claim_alert_raised`.

## Task 1: Synthetic data additions (Phase A)

Goal: extend the generator so every new scenario exists in the data, with an answer key, and so that unrelated busy entities test that the graph does not over-connect.

1. Extend `generate_data.py` with an option that adds the scenarios below to both the full dataset and the demo pack, and appends them to `answer_key.json` under their own section.
2. Cross-claim scenarios:

   | Scenario | Count | Expected result |
   | --- | --- | --- |
   | Same invoice (provider + invoice number) claimed under two different policies by different claimants | 8 pairs | One group, tag `INVOICE_REUSED_ACROSS_POLICIES` |
   | Same incident reference claimed under two policies (double insurance) | 5 pairs | One group, tag `INCIDENT_CLAIMED_TWICE` |
   | Same claimant, overlapping hospital stays at two providers | 4 pairs | One group, tag `CONCURRENT_STAYS` |
   | Same bill document (identical file or near-identical image) attached to two claims | 3 pairs | One group, tag `DOCUMENT_REUSED` |
   | Chain: claim A shares an invoice with B, B shares an incident with C | 2 chains | One group of 3 claims |
   | Controls: a busy provider with 200+ unrelated claims; a family policy with 4 members claiming separately; weekly physiotherapy (cleared repeats) | Built in | No groups formed from these alone |

3. Documents for about 40 demo-pack claims (reuse the invoice templates, add a discharge summary template):
   - Invoice PDFs in two layouts, plus 3 scanned images.
   - Discharge summaries (PDF): patient, hospital, admission and discharge dates, diagnosis, procedures performed, treating doctor.
   - Stretch: 3 motor repair estimates for an optional `motor` claim type.
4. Planted document discrepancies (recorded in the answer key with the expected type and amount):

   | Discrepancy | Count |
   | --- | --- |
   | Claim line amount higher than the invoice | 6 |
   | Line in claim but not on the invoice | 5 |
   | Line on the invoice but not in the claim (benign) | 3 |
   | Quantity or unit price mismatch | 4 |
   | Service date mismatch | 3 |
   | Invoice number on document differs from claim | 2 |
   | Patient name on document differs from claimant | 2 |
   | Discharge summary stay shorter than room days billed | 4 |
   | Procedure billed but not mentioned in the discharge summary | 3 |
   | Clean documents that match exactly | about 10 |

5. Make several claims carry several issues at once (a duplicate line plus a sub-limit breach plus a co-pay), so Task 5's sequencing is tested.

Acceptance criteria:

- Every scenario exists with the stated count and an answer-key entry (test).
- Clean documents match their claims exactly (test).
- Same seed produces identical files and documents.

## Task 2: Cross-claim correlation graph (Phase B)

Goal: connect claims through shared identifiers, group related claims, and explain every connection with the exact matching attributes, without letting busy providers or policies connect everything.

1. Nodes (`nodes.py`): one node per distinct entity, keyed on normalised identifiers.

   | Node type | Key |
   | --- | --- |
   | claim | claim_id |
   | policy | policy_number |
   | claimant | claimant_id |
   | provider | provider_id |
   | invoice | provider_id + normalised invoice reference |
   | incident | normalised incident reference |
   | document | SHA-256; near-identical images merged when perceptual-hash distance ≤ 5 |

2. Edges (`edges.py`): claim-to-entity edges are structural; relationships between claims are derived from them.

   | Claim-claim link | Strength | Evidence stored |
   | --- | --- | --- |
   | Share an invoice node | Strong | Provider, invoice number as written on each claim, line amounts |
   | Share an incident node | Strong | Incident reference as written, incident dates, policies |
   | Share a document node | Strong | File names, hashes, hash distance |
   | Exact or near-duplicate match (flagged) | Strong | The duplicate signals and score |
   | Same claimant, overlapping service periods | Strong | Both date ranges, providers |
   | Same claimant + same provider within 7 days (not a cleared repeat) | Weak | Dates, gap |
   | Same policy + same provider within 7 days, different claimants | Weak | Dates, claimants |
   | Similar amount (±2%) + same provider within 30 days | Weak | Amounts, dates |

   Hub rule: provider and policy nodes are never traversed to relate claims; only the specific link rules above create claim-claim relationships.
   Pairs cleared as legitimate repeats never produce a link.

3. Groups (`groups.py`):
   - Build a claim-claim graph in networkx from strong links, plus weak links only where a pair has two or more weak links.
   - Each connected component with 2+ claims is a relationship group (`REL-…`), with a stable ID derived from its sorted claim IDs.
   - Tags from the link types: `INVOICE_REUSED_ACROSS_POLICIES`, `INCIDENT_CLAIMED_TWICE`, `CONCURRENT_STAYS`, `DOCUMENT_REUSED`, `DUPLICATE_CLUSTER`, `WEAK_PATTERN`.
   - Summary from a template, e.g. "Invoice INV452 from Apollo Chennai (PRV-0012) appears in CLM-000123 under POL-000045 (R. Kumar) and CLM-000876 under POL-000310 (S. Iyer); both bill ₹48,500 for the same services on 12 Oct."
   - Groups are versioned per build; a group whose membership is unchanged keeps its ID.
4. Cross-claim alerts (`alerts.py`), written to the alerts table with new categories:

   | Category | Amount type | Amount |
   | --- | --- | --- |
   | CROSS_POLICY_INVOICE_REUSE | Calculated | Later claim's amount for the shared invoice lines |
   | INCIDENT_CLAIMED_TWICE | Estimated | The smaller of the two claimed amounts |
   | CONCURRENT_STAYS | Suspected | None |
   | DOCUMENT_REUSED | Calculated | Amount of the later claim supported by the reused document |

   Each alert's `supporting` field lists the group ID, the edges and the matched records.
5. API and UI:
   - `GET /claims/{id}/related`: the claim's groups, plus the subgraph (nodes and edges up to 2 hops, with provider and policy nodes shown but not expanded).
   - `GET /relationship-groups` (filter by tag, claim count, policy count, amount) and `GET /relationship-groups/{id}`.
   - `RelatedClaimsGraph` component: claims as cards, entity nodes as icons, edges coloured by strength and labelled by link type.
     Clicking an edge shows its evidence; clicking a node lists its records (claims, lines, documents).

Acceptance criteria:

- Every planted relationship is found in the right group with the right tag (test against the answer key).
- The control scenarios (busy provider, family policy, cleared repeats) produce no groups on their own (test).
- Every edge has evidence naming the matched fields and values; no edge is created by the LLM.
- A full graph build over the sample data takes under 30 seconds.
- Rebuilding without data changes keeps the same group IDs.

## Task 3: Document extraction with source references (Phase C)

Goal: turn each supporting document into structured, validated values where every value points to the exact page and location it came from.

1. `POST /claims/{id}/documents` (multipart, PDF / PNG / JPEG, max 15 MB): validate the type from the bytes, store in Spaces at `claims/{claim_id}/docs/{document_id}.{ext}`, compute SHA-256 and perceptual hash, create the `documents` row, and start extraction in the background.
2. Classify (`classify.py`): Claude Haiku labels the document from its first page's text: `invoice`, `discharge_summary`, `repair_estimate`, `other`.
   A user can override the type in the API.
3. Parse with Docling: keep every text item with its page and bounding box.
   Pages with fewer than about 200 characters, and image files, are rendered at 200 DPI (pypdfium2) and sent to Claude vision; for those pages, store the page number and mark bounding boxes unavailable.
4. Extraction schemas (`schemas.py`), each field returned as `{value, source_quote, page}`:

   | Document | Fields |
   | --- | --- |
   | Invoice | invoice_number, provider_name, invoice_date, patient_name, policy_number (if printed), admission_date, discharge_date, lines (description, service_code, service_date, quantity, unit_price, amount), subtotal, taxes, total |
   | Discharge summary | patient_name, hospital_name, admission_date, discharge_date, diagnosis (text and ICD-10 if printed), procedures_performed (list), treating_doctor |
   | Repair estimate (stretch) | vehicle_registration, workshop_name, estimate_date, lines (part or labour, description, quantity, unit_price, amount), total |

5. Extract (`extract.py`) with Claude Haiku using structured output.
   Document text is wrapped in `<untrusted_document>` tags; the system prompt says its content is data, never instructions, and that every value must come with the exact text it was read from.
6. Provenance check (`provenance.py`): find each `source_quote` in the Docling text items of the stated page (normalise whitespace and case; allow fuzzy match ≥ 90 for OCR noise).
   Found → `verified` with that item's bounding box.
   Not found → `unverified`, and the value is excluded from comparisons that compute money.
   This prevents invented values from entering the analysis.
   Docling's OCR text is used for scanned pages where available; for handwritten pages read only by vision, status is `page_only`: usable in comparisons, but any resulting discrepancy amount is marked estimated rather than calculated.
7. Normalise and validate: dates and amounts parsed (shared helpers); for invoices, lines sum to subtotal and subtotal + taxes = total (±₹1); quantity × unit price = amount; discharge on or after admission.
   Failures set `needs_review` with the errors; one automatic retry includes the errors in the prompt.
8. Store `document_extractions`, `extracted_fields` and `extracted_lines`; write an `extraction_created` event with model and prompt version.
   Re-extracting creates a new version; earlier versions remain.
9. `GET /documents/{id}/extraction` (latest, or `?version=`) returns fields and lines with provenance; `GET /documents/{id}/file` returns a presigned URL.

Acceptance criteria:

- At least 95% of the sample invoices and discharge summaries extract with validations passing.
- At least 95% of extracted fields on clean PDFs are `verified` with a bounding box.
- A value whose quote does not exist in the document is marked `unverified` (test with a tampered model response).
- The prompt-injection canary document has no effect on extracted values (test).
- Scanned samples route to vision and still produce page references.

## Task 4: Document-to-claim comparison (Phase D)

Goal: find every difference between a claim's records and its supporting documents, with both values, both sources and the money impact.

1. Header checks (invoice vs claim):

   | Check | Rule | Discrepancy type |
   | --- | --- | --- |
   | Invoice number | Normalised document number equals one of the claim's invoice references | `INVOICE_REF_MISMATCH` |
   | Provider | Document provider name fuzzy-matches the claim lines' provider (≥ 85) | `PROVIDER_MISMATCH` |
   | Patient | Document patient name fuzzy-matches the claimant (≥ 85) | `PATIENT_MISMATCH` |
   | Dates | Admission and discharge (or invoice date) consistent with incident and service dates | `DATE_MISMATCH` |
   | Total | Document total vs sum of the claim lines for that invoice | `TOTAL_MISMATCH` |

2. Line matching (`matching.py`):
   - Build a cost matrix between claim lines (for that invoice) and document lines.
     Similarity = 0.40 × code match (1 if equal) + 0.30 × description similarity (rapidfuzz `token_set_ratio`) + 0.20 × amount closeness + 0.10 × same service date.
   - Solve with `scipy.optimize.linear_sum_assignment`; accept pairs with similarity ≥ 0.60.
   - Unresolved lines with similarity 0.40-0.60: ask Claude Haiku whether they describe the same service (e.g. "CT Brain Plain" vs "CT Head without contrast"), returning yes / no and a confidence.
     Accepted AI matches are stored with `generated_by = ai` and shown as "AI-suggested match".
   - Store all pairs and unmatched lines in `document_comparisons.line_matches`.
3. Line discrepancies:

   | Type | When | Amount impact |
   | --- | --- | --- |
   | `AMOUNT_MISMATCH` | Matched pair, claim amount ≠ document amount | Calculated: claim − document (when the claim is higher); raised only when a quantity or unit-price difference does not already explain it |
   | `QUANTITY_MISMATCH` | Matched pair, quantities differ | Calculated: (claim qty − doc qty) × unit price |
   | `UNIT_PRICE_MISMATCH` | Matched pair, unit prices differ | Calculated: (claim price − doc price) × qty |
   | `SERVICE_DATE_MISMATCH` | Matched pair, dates differ | None (informational) |
   | `ONLY_IN_CLAIM` | Claim line with no document counterpart | Calculated: full line amount (unsupported charge) |
   | `ONLY_IN_DOCUMENT` | Document line not claimed | None (informational, usually benign) |

4. Cross-document checks (discharge summary vs claim):

   | Type | Rule | Amount impact |
   | --- | --- | --- |
   | `STAY_LENGTH_MISMATCH` | Room or ICU days billed > discharge − admission days | Calculated: extra days × room rate |
   | `PROCEDURE_NOT_DOCUMENTED` | A billed procedure line is not supported by the summary. Claude Haiku checks each procedure line against the summary text and must return a supporting quote or "not found"; a quote is accepted only if it exists in the summary | Estimated: the line amount |

5. Output:
   - One `document_discrepancies` row per finding (`DSC-…`), with claim value, document value, difference, amount impact and type, severity (existing thresholds), `claim_ref` (claim, line, source row) and `document_ref` (document, page, bbox, quote).
   - A `comparison_created` event per run.
   - Discrepancies with an amount impact also create an alert in a new category `DOCUMENT_DISCREPANCY`, so they appear on the existing dashboard.
   - `GET /claims/{id}/document-comparison` returns matched pairs, unmatched lines and discrepancies, ready for the `DocumentComparison` component.

Acceptance criteria:

- Every planted document discrepancy is detected with the expected type and amount (test against the answer key).
- Clean documents produce no discrepancies except benign `ONLY_IN_DOCUMENT` lines.
- Every discrepancy has a document reference with page (and bounding box where available).
- AI-suggested matches and AI-assessed procedure checks are labelled and store their quotes.
- `DocumentComparison` shows both values side by side and jumps to the document location.

## Task 5: Recommended settlement corrections (Phase E)

Goal: for each flagged claim, produce an ordered list of specific corrections that take the requested amount to a recommended payable amount, where every step shows the original amount, corrected amount, calculation and the policy rule or evidence behind it, and the totals reconcile exactly.

The key design point: corrections interact.
Removing a duplicate line changes the sub-limit excess, which changes the co-pay.
So corrections are not computed independently; they are produced by re-running the payable calculator on a corrected line set, and each step's reduction becomes one correction.
This prevents double counting.

Algorithm (`builder.py`):

1. Collect inputs: claim lines; validation results; flagged duplicate matches; calculated cross-claim alerts; document discrepancies with a calculated amount and verified (or page-only) provenance.
2. Claim-level stop: if the claim is an exact duplicate, reuses another claim's invoice or document in full, is outside the benefit period, or the claimant isn't insured, produce a single `SET_PAYABLE_TO_ZERO` correction and stop.
3. Line-level corrections, at most one per line, in priority order: remove duplicate line → remove unsupported line (`ONLY_IN_CLAIM`, only when the invoice's document is present) → adjust to document amount, quantity or price → reduce room days to the documented stay.
4. Policy corrections: run the payable calculator on the corrected lines.
   Each reducing step becomes a correction: remove excluded or uncovered line, cap at sub-limit, apply deductible, apply co-pay, cap at remaining overall limit.
5. Sequence all corrections in the order applied; store `original_amount` and `corrected_amount` as the running amount before and after each step.
6. Reconcile: requested − sum of differences = recommended payable, exactly.
   The builder raises an error if not.
7. Settled claims: add `RECOVER_OVERPAYMENT` = paid − recommended payable (when positive), and store it as `recovery_amount` on the set.
8. Estimated and suspected items (procedure not documented, near-duplicates, incident claimed twice) are listed as corrections with `applied = false`: shown for review, never included in the recommended payable.

Correction types and calculation templates:

| Type | Example calculation text | Support |
| --- | --- | --- |
| `REMOVE_DUPLICATE_LINE` | Line 4 "CT Brain" ₹6,500 repeats line 3 (same code, date, quantity, price): ₹6,500 → ₹0 | Duplicate match |
| `REMOVE_UNSUPPORTED_LINE` | "Nebulisation" ₹1,200 not on invoice INV452: ₹1,200 → ₹0 | Document discrepancy |
| `ADJUST_TO_DOCUMENT` | Claimed ₹12,000; invoice shows ₹9,500 (page 1): ₹12,000 → ₹9,500 | Document discrepancy |
| `REDUCE_ROOM_DAYS` | Billed 5 days × ₹4,000; discharge summary shows 3 days: ₹20,000 → ₹12,000 | Document discrepancy |
| `REMOVE_EXCLUDED_LINE` | Cosmetic procedure excluded: ₹35,000 → ₹0 | Policy rule |
| `CAP_AT_SUB_LIMIT` | (₹7,000 − ₹5,000) × 3 days = ₹6,000: ₹21,000 → ₹15,000 | Policy rule |
| `APPLY_DEDUCTIBLE` | ₹1,20,000 − ₹10,000 deductible: ₹1,20,000 → ₹1,10,000 | Policy rule |
| `APPLY_COPAY` | 10% × ₹1,10,000 = ₹11,000: ₹1,10,000 → ₹99,000 | Policy rule |
| `CAP_AT_OVERALL_LIMIT` | Remaining limit ₹80,000: ₹99,000 → ₹80,000 | Policy rule + settlements |
| `SET_PAYABLE_TO_ZERO` | Invoice INV452 already claimed in CLM-000123 (paid ₹48,500): ₹48,500 → ₹0 | Duplicate or cross-claim alert |
| `RECOVER_OVERPAYMENT` | Paid ₹84,000 − recommended ₹75,600 = ₹8,400 recoverable | Settlement record |

Each row also stores the structured calculation (formula and inputs), the policy rule ID where applicable, and `evidence_refs` listing the finding IDs (`ALR-…`, `DSC-…`, `REL-…`) it relies on.

Versioning and API:

- Each build creates a new `correction_set` version only when its `inputs_hash` (hash of all inputs) changes; earlier versions are never modified.
- A `correction_set_created` event is written with the version and totals.
- `GET /claims/{id}/corrections` (latest), `?version=N`, `GET /claims/{id}/corrections/versions`, `POST /claims/{id}/corrections/recompute`.
- `CorrectionsTable` component: requested amount at the top, one row per correction (type, line, original, corrected, difference, calculation, rule or evidence chip), recommended payable at the bottom, and unapplied items in a separate "For review" section.
- Optional: a plain-language summary written by Claude from the structured corrections, with the number guardrail (every number must appear in the input).

Acceptance criteria:

- For every planted scenario, the expected correction type and amount are produced (test against the answer key).
- Multi-issue claims match a hand-computed worked example exactly, with no double counting (test).
- Requested − sum of applied differences = recommended payable for every claim (test).
- Estimated items never change the recommended payable (test).
- Recomputing with unchanged inputs creates no new version; changing a line creates version + 1 and leaves the old version intact (test).

## Task 6: Integration contract and demo pages

The teammate builds the workspace, decisions and audit trail against these guarantees, so neither side blocks the other.

What this plan guarantees:

1. One investigation bundle per claim: `GET /claims/{id}/investigation` returns everything the workspace needs in one call: claim and lines, the policy and the policy rules that were applied, validation results and alerts, related groups with subgraph, documents with latest extractions and provenance, the latest document comparison and discrepancies, the latest correction set, and a leakage summary (calculated, estimated, recovery).
2. Stable finding IDs: every reviewable item has an ID with a type prefix (`ALR-`, `DSC-`, `REL-`, `COR-`).
   A decision references `(finding_id, finding_version)`.
3. Immutability: extractions, comparisons, discrepancies, groups and correction sets are never updated or deleted.
   The original recommendation therefore always exists, which is what capability 6 requires when an analyst overrides it.
4. Machine-generated history: `analysis_events` records every system and AI step with timestamp, model and prompt version.
   The audit trail merges these with the teammate's user events.
5. AI labelling: every AI-produced item carries `generated_by = ai`, model, prompt version and its supporting quote, so the report can separate AI recommendations from rule-based ones.
6. Evidence export: `GET /claims/{id}/evidence.json` returns the full investigation bundle plus all versions and events, as the data source for the downloadable report.
7. Reusable components: `RelatedClaimsGraph`, `DocumentComparison` and `CorrectionsTable` accept a claim ID (or bundle data) as props and contain no page-level routing or auth logic.

What the teammate owns:

- Authentication, roles and replacing `get_current_user()`.
- A `finding_decisions` table, suggested shape: decision_id, finding_id, finding_version, decision (`confirm_discrepancy`, `false_positive`, `request_evidence`, `escalate_senior`, `escalate_siu`, `accept_correction`), reason (required for false positive and overrides), override values, decided_by, decided_at.
  Append-only; the latest row is the current state.
- Applying an accepted correction to a final settlement amount (a new record, never by editing the correction set).
- Investigation notes, the workspace layout, the audit-trail view and the PDF report.

Agreed up front:

- Finding ID prefixes and the `finding_decisions` shape above.
- The investigation bundle's JSON schema (generated from the Pydantic response model and shared through the OpenAPI file).
- Decisions never call back into analysis tables; if analysis is recomputed, existing decisions stay attached to the version they were made on.

## API contract

All new routes are under `/api/v1`, use `get_current_user()`, and return Pydantic models published in the OpenAPI file.

| Method | Path | Task | Purpose |
| --- | --- | --- | --- |
| POST | `/claims/{id}/documents` | 3 | Upload a supporting document; starts classification and extraction |
| GET | `/claims/{id}/documents` | 3 | Documents for a claim with type, status and latest extraction version |
| GET | `/documents/{id}/extraction` | 3 | Latest extraction (or `?version=N`) with fields, lines and provenance |
| PATCH | `/documents/{id}` | 3 | Override document type, then re-extract (new version) |
| GET | `/documents/{id}/file` | 3 | Presigned URL (5 minutes) |
| GET | `/claims/{id}/document-comparison` | 4 | Matched pairs, unmatched lines and discrepancies (latest or `?version=N`) |
| GET | `/discrepancies/{id}` | 4 | One discrepancy with claim and document references |
| POST | `/graph/rebuild` | 2 | Rebuild the graph for all claims or `{claim_ids}` |
| GET | `/claims/{id}/related` | 2 | Groups containing the claim, plus its subgraph |
| GET | `/relationship-groups` | 2 | Filter by tag, claim count, policy count, amount |
| GET | `/relationship-groups/{id}` | 2 | Group members, edges with evidence, summary |
| GET | `/graph/nodes/{node_id}/records` | 2 | Records behind a node (claims, lines, documents) |
| GET | `/claims/{id}/corrections` | 5 | Latest correction set (or `?version=N`) |
| GET | `/claims/{id}/corrections/versions` | 5 | All versions with totals and timestamps |
| POST | `/claims/{id}/corrections/recompute` | 5 | Rebuild; creates a new version only if inputs changed |
| GET | `/claims/{id}/investigation` | 6 | The full bundle for the workspace |
| GET | `/claims/{id}/evidence.json` | 6 | Bundle plus all versions and events, for the report |
| GET | `/claims/{id}/events` | 6 | Machine-generated history for the audit trail |

## Acceptance tests and demo script

Capabilities 1, 2 and 4 are done when every row passes as an automated test against the answer key and can be shown live.

| # | Requirement | Automated test | Shown in demo |
| --- | --- | --- | --- |
| 1 | Relationships among claims, policies, claimants, providers, invoices, incidents | Every planted relationship found in the correct group with the correct tag | Graph of a cross-policy invoice pair |
| 2 | Related claims presented together | Groups list and claim view return all members | Group page with members side by side |
| 3 | Matching attributes explained | Every edge has evidence naming fields and values | Click an edge: "Same invoice INV452 from PRV-0012" |
| 4 | No false connections through busy entities | Control scenarios produce no groups | Busy provider shown, not expanded |
| 5 | Extract from invoices and discharge summaries | ≥ 95% pass validation | Upload an invoice and a discharge summary |
| 6 | Every extracted value keeps its source | ≥ 95% verified with page and box; invented quotes rejected | Click a value: the PDF jumps to it |
| 7 | Differences between document and claim | Every planted discrepancy detected with type and amount | Side-by-side comparison with highlights |
| 8 | Specific corrections, not warnings | Every planted scenario gets the expected correction type and amount | Corrections table for a multi-issue claim |
| 9 | Original, corrected, calculation and rule on each | Every correction row has all four | Row: (₹7,000 − ₹5,000) × 3 = ₹6,000 with rule ID |
| 10 | Totals reconcile, no double counting | Reconciliation holds for every claim | Requested → recommended payable |
| 11 | Original recommendation preserved | Recompute keeps old versions intact | Versions list |

Demo script (about 4 minutes):

1. Correlation (75 s): open a flagged claim and its related-claims graph.
   Two claims under different policies and different claimants share invoice INV452 from the same hospital; click the edge to show the matching fields.
   Then show a chain of three claims linked by an invoice and an incident, and point out that the hospital node connects hundreds of claims but is not used to relate them.
2. Documents (75 s): upload the invoice and discharge summary for a claim.
   Show the extraction with every value linked to its place in the PDF.
   The comparison highlights a line claimed at ₹12,000 that the invoice shows at ₹9,500, a "Nebulisation" charge not on the invoice, and 5 room days billed against a 3-day stay in the discharge summary.
3. Corrections (60 s): open the corrections table for the same claim.
   Walk from requested to recommended payable: adjust to invoice (−₹2,500), remove unsupported line (−₹1,200), reduce room days (−₹8,000), cap at sub-limit, apply deductible, apply co-pay, each with its calculation and rule or evidence.
   The totals reconcile exactly.
   Show the "For review" section with an estimated item that was not applied.
4. Handover (15 s): these results are versioned and immutable, ready for the analyst's decisions and audit trail.
