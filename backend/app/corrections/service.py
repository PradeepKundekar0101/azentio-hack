"""Build and store a claim's correction set from what the other stages found: failed eligibility checks, flagged
duplicates, cross-claim alerts and document discrepancies. The payable calculator re-runs with the policy's other
claims, so per-period and overall limits see the same ledger as the rule engine."""

import hashlib
import json
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.build import CHECK_CATEGORY
from app.alerts.finding import alert_finding_id
from app.core.enums import AlertCategory, AmountType, EventType, GeneratedBy, MatchDecision, MatchType, Outcome
from app.core.money import inr
from app.corrections.builder import CorrectionInputs, CorrectionPlan, LineAction, Stop, build_corrections
from app.corrections.types import LINE_PRIORITY, CorrectionType
from app.db.models import Alert, Correction, CorrectionSet, DocumentDiscrepancy, DuplicateMatch, ValidationResult
from app.documents.compare import qty
from app.documents.comparison_service import latest_comparisons
from app.events import event, write_events
from app.rules.checks import CHECKS
from app.rules.context import ClaimData, Evaluation, LineData
from app.rules.payable import evaluate_policy

STOP_CHECKS = ("C01", "C02", "C03")
ADJUST_TYPES = {"AMOUNT_MISMATCH", "QUANTITY_MISMATCH", "UNIT_PRICE_MISMATCH"}
FULL_REUSE = {AlertCategory.CROSS_POLICY_INVOICE_REUSE.value, AlertCategory.DOCUMENT_REUSED.value}


def correction_id(claim_id: str, kind: str, line_id: str | None, rule_id: str | None, applied: bool) -> str:
    key = "|".join((claim_id, kind, line_id or "", rule_id or "", "applied" if applied else "review"))
    return f"COR-{hashlib.sha256(key.encode()).hexdigest()[:12].upper()}"


class Evidence:
    """Everything the corrections of one claim rely on, read from the other stages' results."""

    def __init__(self) -> None:
        self.failed: list[ValidationResult] = []
        self.matches: list[DuplicateMatch] = []
        self.alerts: list[Alert] = []
        self.discrepancies: list[DocumentDiscrepancy] = []


async def load_evidence(session: AsyncSession, claim_ids: list[str]) -> dict[str, Evidence]:
    found: dict[str, Evidence] = defaultdict(Evidence)
    for start in range(0, len(claim_ids), 5000):
        ids = claim_ids[start : start + 5000]
        for r in await session.scalars(
            select(ValidationResult).where(
                ValidationResult.claim_id.in_(ids), ValidationResult.outcome == Outcome.FAIL.value
            )
        ):
            found[r.claim_id].failed.append(r)
        for m in await session.scalars(
            select(DuplicateMatch).where(DuplicateMatch.claim_id.in_(ids)).order_by(DuplicateMatch.id)
        ):
            found[m.claim_id].matches.append(m)
        for a in await session.scalars(select(Alert).where(Alert.claim_id.in_(ids)).order_by(Alert.id)):
            found[a.claim_id].alerts.append(a)
    for claim_id in claim_ids:
        comparisons = await latest_comparisons(session, claim_id)
        if comparisons:
            found[claim_id].discrepancies = list(
                await session.scalars(
                    select(DocumentDiscrepancy)
                    .where(DocumentDiscrepancy.comparison_id.in_([c.comparison_id for c in comparisons]))
                    .order_by(DocumentDiscrepancy.discrepancy_id)
                )
            )
    return found


def _alert_id(evidence: Evidence, category: str, line_id: str | None = None) -> list[str]:
    ids = [
        a.finding_id for a in evidence.alerts if a.category == category and (line_id is None or a.line_id == line_id)
    ]
    return ids[:1]


def _stop(claim: ClaimData, evidence: Evidence) -> Stop | None:
    for m in evidence.matches:
        if m.match_type == MatchType.EXACT_CLAIM.value and m.decision == MatchDecision.FLAGGED.value:
            return Stop(
                f"Exact duplicate of {m.matched_claim_id}",
                _alert_id(evidence, AlertCategory.EXACT_DUPLICATE_CLAIM.value),
            )
    line_total = sum((ln.line_amount for ln in claim.lines), Decimal(0))
    for a in evidence.alerts:
        if a.category in FULL_REUSE and a.amount is not None and a.amount >= line_total:
            group = a.supporting.get("group_id")
            refs = [a.finding_id, *([group] if group else [])]
            return Stop(a.explanation, refs)
    for code in STOP_CHECKS:
        result = next((r for r in evidence.failed if r.check_code == code), None)
        if result is not None:
            category = CHECK_CATEGORY[code].value
            refs = _alert_id(evidence, category) or [
                alert_finding_id(
                    claim.claim_id, category, result.line_id, f"{code} {CHECKS[code]}", result.policy_rule_id, None
                )
            ]
            return Stop(result.explanation, refs)
    return None


def _room_reductions(lines: list[LineData], days: Decimal, ref: str, explanation: str) -> list[LineAction]:
    """Reduce room days, latest first, until `days` are taken off."""
    actions = []
    remaining = days
    for line in sorted(
        (ln for ln in lines if ln.category == "room"), key=lambda ln: (ln.service_date, ln.line_id), reverse=True
    ):
        if remaining <= 0:
            break
        cut = min(line.quantity, remaining)
        remaining -= cut
        quantity = line.quantity - cut
        text = (
            f'"{line.service_description}" billed {qty(line.quantity)} days × {inr(line.unit_price)}; '
            f"{qty(cut)} beyond the stay in the discharge summary"
        )
        actions.append(
            LineAction(
                line.line_id,
                CorrectionType.REDUCE_ROOM_DAYS,
                quantity * line.unit_price,
                [ref],
                explanation,
                corrected_quantity=quantity,
                corrected_unit_price=line.unit_price,
                calculation_text=text,
            )
        )
    return actions


def _actions(claim: ClaimData, evidence: Evidence) -> list[LineAction]:
    lines = {ln.line_id: ln for ln in claim.lines}
    candidates: dict[str, list[LineAction]] = defaultdict(list)
    review: list[LineAction] = []
    for m in evidence.matches:
        if m.decision != MatchDecision.FLAGGED.value:
            continue
        if m.match_type == MatchType.DUPLICATE_LINE.value and m.line_id in lines:
            line = lines[m.line_id]
            repeated = m.matched_line_id or m.matched_claim_id
            text = f'Line {line.line_id} "{line.service_description}" {inr(line.line_amount)} repeats {repeated}'
            candidates[line.line_id].append(
                LineAction(
                    line.line_id,
                    CorrectionType.REMOVE_DUPLICATE_LINE,
                    Decimal(0),
                    _alert_id(evidence, AlertCategory.DUPLICATE_LINE_ITEM.value, line.line_id),
                    m.reason,
                    calculation_text=text,
                )
            )
        elif m.match_type == MatchType.NEAR_DUPLICATE.value and not (m.signals or {}).get("excess_frequency"):
            amount = Decimal((m.signals or {}).get("overlapping_amount", "0"))
            review.append(
                LineAction(
                    None,
                    CorrectionType.REMOVE_DUPLICATE_LINE,
                    Decimal(0),
                    _alert_id(evidence, AlertCategory.NEAR_DUPLICATE.value),
                    f"Overlapping services with {m.matched_claim_id} (near-duplicate)",
                    applied=False,
                    amount_type=AmountType.ESTIMATED.value,
                    amount=amount,
                )
            )
    for a in evidence.alerts:
        if a.category == AlertCategory.INCIDENT_CLAIMED_TWICE.value and a.amount is not None:
            group = a.supporting.get("group_id")
            review.append(
                LineAction(
                    None,
                    CorrectionType.SET_PAYABLE_TO_ZERO,
                    Decimal(0),
                    [a.finding_id, *([group] if group else [])],
                    a.explanation,
                    applied=False,
                    amount_type=AmountType.ESTIMATED.value,
                    amount=a.amount,
                )
            )
    adjust: dict[str, list[DocumentDiscrepancy]] = defaultdict(list)
    for d in evidence.discrepancies:
        line_id = d.claim_ref.get("line_id")
        usable = d.amount_impact is not None and d.amount_impact > 0
        if d.type == "PROCEDURE_NOT_DOCUMENTED" and line_id in lines:
            review.append(
                LineAction(
                    line_id,
                    CorrectionType.REMOVE_UNSUPPORTED_LINE,
                    Decimal(0),
                    [d.discrepancy_id],
                    d.explanation,
                    applied=False,
                    amount_type=AmountType.ESTIMATED.value,
                )
            )
        elif not usable or line_id not in lines:
            continue
        elif d.amount_type != AmountType.CALCULATED.value:  # read from an image: listed for review
            review.append(
                LineAction(
                    line_id,
                    CorrectionType.ADJUST_TO_DOCUMENT,
                    lines[line_id].line_amount - d.amount_impact,
                    [d.discrepancy_id],
                    d.explanation,
                    applied=False,
                    amount_type=AmountType.ESTIMATED.value,
                )
            )
        elif d.type == "ONLY_IN_CLAIM":
            line = lines[line_id]
            text = f'"{line.service_description}" {inr(line.line_amount)} is not on the invoice'
            candidates[line_id].append(
                LineAction(
                    line_id,
                    CorrectionType.REMOVE_UNSUPPORTED_LINE,
                    Decimal(0),
                    [d.discrepancy_id],
                    d.explanation,
                    calculation_text=text,
                )
            )
        elif d.type in ADJUST_TYPES:
            adjust[line_id].append(d)
        elif d.type == "STAY_LENGTH_MISMATCH":
            days = d.difference or Decimal(0)
            for action in _room_reductions(list(claim.lines), days, d.discrepancy_id, d.explanation):
                candidates[action.line_id].append(action)  # type: ignore[index]
    for line_id, items in adjust.items():
        line = lines[line_id]
        corrected = line.line_amount - sum((d.amount_impact or Decimal(0) for d in items), Decimal(0))
        quantity = next(
            (Decimal(d.document_value) for d in items if d.type == "QUANTITY_MISMATCH" and d.document_value), None
        )
        price = next(
            (Decimal(d.document_value) for d in items if d.type == "UNIT_PRICE_MISMATCH" and d.document_value), None
        )
        text = f"Claimed {inr(line.line_amount)}; the invoice shows {inr(corrected)}"
        candidates[line_id].append(
            LineAction(
                line_id,
                CorrectionType.ADJUST_TO_DOCUMENT,
                corrected,
                [d.discrepancy_id for d in items],
                "; ".join(d.explanation for d in items),
                corrected_quantity=quantity,
                corrected_unit_price=price,
                calculation_text=text,
            )
        )
    chosen = []
    for line_id in lines:
        options = sorted(candidates.get(line_id, []), key=lambda a: LINE_PRIORITY.index(CorrectionType(a.type)))
        if options:
            chosen.append(options[0])
    # Applied in priority order (all repeated lines first, then unsupported ones, ...), then by line.
    chosen.sort(key=lambda a: (LINE_PRIORITY.index(CorrectionType(a.type)), a.line_id or ""))
    return chosen + review


def plan_for(
    claim: ClaimData, policy_claims: list[ClaimData], policy: Any, rules: tuple, evidence: Evidence
) -> CorrectionPlan:
    def payable(corrected: list[LineData]) -> Evaluation:
        target = replace(
            claim, lines=tuple(corrected), requested_amount=sum((ln.line_amount for ln in corrected), Decimal(0))
        )
        claims = [target if c.claim_id == claim.claim_id else c for c in policy_claims]
        return next(e for e in evaluate_policy(policy, rules, claims) if e.claim_id == claim.claim_id)

    stop = _stop(claim, evidence)
    settlement = claim.settlement if claim.status == "settled" else None
    inputs = CorrectionInputs(
        claim,
        [] if stop else _actions(claim, evidence),
        stop=stop,
        paid=settlement.paid_amount if settlement else None,
        approved=settlement.approved_amount if settlement else None,
        settlement_refs=[settlement.settlement_id] if settlement else [],
    )
    return build_corrections(inputs, payable)


def plan_hash(plan: CorrectionPlan) -> str:
    """Hash of the set's content: a new version is written only when this changes."""
    body = {
        "requested": str(plan.requested),
        "recommended": str(plan.recommended_payable),
        "paid": str(plan.paid),
        "corrections": [
            [
                c.type,
                c.line_id,
                str(c.original_amount),
                str(c.corrected_amount),
                c.policy_rule_id,
                c.evidence_refs,
                c.applied,
                c.calculation_text,
            ]
            for c in plan.corrections
        ],
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


async def store_plan(
    session: AsyncSession, claim_id: str, plan: CorrectionPlan, run_id: int | None
) -> tuple[CorrectionSet, bool]:
    digest = plan_hash(plan)
    latest = await session.scalar(
        select(CorrectionSet).where(CorrectionSet.claim_id == claim_id).order_by(CorrectionSet.version.desc()).limit(1)
    )
    if latest is not None and latest.inputs_hash == digest:
        return latest, False
    correction_set = CorrectionSet(
        claim_id=claim_id,
        version=(latest.version if latest else 0) + 1,
        requested_amount=plan.requested,
        recommended_payable=plan.recommended_payable,
        total_reduction=plan.total_reduction,
        paid_amount=plan.paid,
        recovery_amount=plan.recovery_amount,
        inputs_hash=digest,
        run_id=run_id,
    )
    session.add(correction_set)
    await session.flush()
    rows = [
        {
            "correction_id": correction_id(claim_id, c.type, c.line_id, c.policy_rule_id, c.applied),
            "set_id": correction_set.set_id,
            "claim_id": claim_id,
            "line_id": c.line_id,
            "sequence": c.sequence,
            "type": c.type,
            "original_amount": c.original_amount,
            "corrected_amount": c.corrected_amount,
            "difference": c.difference,
            "calculation_text": c.calculation_text,
            "calculation": c.calculation,
            "policy_rule_id": c.policy_rule_id,
            "evidence_refs": c.evidence_refs,
            "amount_type": c.amount_type,
            "confidence": None,
            "generated_by": GeneratedBy.RULE.value,
            "applied": c.applied,
            "explanation": c.explanation,
        }
        for c in plan.corrections
    ]
    seen: set[str] = set()
    for row in rows:  # the same kind of step twice on one line (e.g. two sub-limits) keeps distinct IDs
        while row["correction_id"] in seen:
            row["correction_id"] = correction_id(
                claim_id, row["type"], row["line_id"], row["correction_id"], row["applied"]
            )
        seen.add(row["correction_id"])
    if rows:
        await session.execute(insert(Correction.__table__), rows)
    await write_events(
        session,
        [
            event(
                EventType.CORRECTION_SET_CREATED,
                "correction_set",
                correction_set.set_id,
                claim_id=claim_id,
                version=correction_set.version,
                requested=str(plan.requested),
                recommended_payable=str(plan.recommended_payable),
                total_reduction=str(plan.total_reduction),
                recovery=str(plan.recovery_amount) if plan.recovery_amount is not None else None,
                corrections=len(rows),
            )
        ],
    )
    return correction_set, True


def affected(evidence: Evidence) -> bool:
    flagged = any(m.decision == MatchDecision.FLAGGED.value for m in evidence.matches)
    return bool(evidence.alerts or evidence.discrepancies or flagged)


async def build_for_loaded(
    session: AsyncSession,
    loaded: dict[str, Any],
    claim_ids: list[str] | None,
    run_id: int | None,
    only_affected: bool = True,
) -> dict[str, tuple[CorrectionSet, bool]]:
    """Correction sets for claims of already-loaded policies (pipeline.load_claims): every affected claim in scope."""
    wanted = set(claim_ids) if claim_ids is not None else None
    claims = [c for items in loaded["claims"].values() for c in items if wanted is None or c.claim_id in wanted]
    evidence = await load_evidence(session, [c.claim_id for c in claims])
    out: dict[str, tuple[CorrectionSet, bool]] = {}
    for number, policy_claims in loaded["claims"].items():
        policy = loaded["policies"][number]
        rules = tuple(loaded["rules"].get(number, []))
        for claim in policy_claims:
            if wanted is not None and claim.claim_id not in wanted:
                continue
            found = evidence.get(claim.claim_id, Evidence())
            if only_affected and not affected(found):
                continue
            plan = plan_for(claim, policy_claims, policy, rules, found)
            out[claim.claim_id] = await store_plan(session, claim.claim_id, plan, run_id)
    return out


async def latest_set(session: AsyncSession, claim_id: str, version: int | None = None) -> CorrectionSet | None:
    query = select(CorrectionSet).where(CorrectionSet.claim_id == claim_id)
    if version is not None:
        query = query.where(CorrectionSet.version == version)
    return await session.scalar(query.order_by(CorrectionSet.version.desc()).limit(1))
