"""Build a claim's corrections: specific, sequenced steps from the requested amount to a recommended payable amount.

Corrections interact (removing a repeated line changes the sub-limit excess, which changes the co-pay), so they are
never computed one by one. A claim-level stop zeroes the claim. Otherwise the line-level corrections are applied to
the claim's lines, the payable calculator runs on the corrected line set, and each of its reducing steps becomes a
correction. Each step runs from the previous one's corrected amount, and requested - the sum of the applied
differences must equal the recommended payable exactly. Estimated items are listed for review and never applied.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

from app.core.enums import Outcome
from app.core.money import inr, q2
from app.corrections.types import OUTSIDE_RECONCILIATION, CorrectionType
from app.rules.context import ClaimData, Evaluation, LineData

ZERO = Decimal("0.00")
SUB_LIMIT_CODES = ("C06", "C07", "C08")


class ReconciliationError(RuntimeError):
    pass


@dataclass
class LineAction:
    """A line-level correction, or (applied=False) an item for review. line_id None: a claim-level review item."""

    line_id: str | None
    type: str
    corrected_amount: Decimal  # the line's amount after the correction (0 removes it)
    evidence_refs: list[str]
    explanation: str
    applied: bool = True
    amount_type: str = "calculated"
    corrected_quantity: Decimal | None = None
    corrected_unit_price: Decimal | None = None
    calculation_text: str | None = None
    amount: Decimal | None = None  # claim-level review items only


@dataclass
class Stop:
    explanation: str
    evidence_refs: list[str]


@dataclass
class CorrectionInputs:
    claim: ClaimData
    actions: list[LineAction]
    stop: Stop | None = None
    paid: Decimal | None = None
    approved: Decimal | None = None
    settlement_refs: list[str] = field(default_factory=list)


@dataclass
class PlannedCorrection:
    sequence: int
    type: str
    line_id: str | None
    original_amount: Decimal
    corrected_amount: Decimal
    difference: Decimal
    calculation_text: str
    calculation: dict[str, Any]
    policy_rule_id: str | None
    evidence_refs: list[str]
    amount_type: str
    applied: bool
    explanation: str


@dataclass
class CorrectionPlan:
    requested: Decimal
    recommended_payable: Decimal
    corrections: list[PlannedCorrection] = field(default_factory=list)
    paid: Decimal | None = None
    recovery_amount: Decimal | None = None

    @property
    def applied(self) -> list[PlannedCorrection]:
        return [c for c in self.corrections if c.applied and c.type not in OUTSIDE_RECONCILIATION]

    @property
    def for_review(self) -> list[PlannedCorrection]:
        return [c for c in self.corrections if not c.applied]

    @property
    def recovery(self) -> PlannedCorrection | None:
        return next((c for c in self.corrections if c.type == CorrectionType.RECOVER_OVERPAYMENT), None)

    @property
    def total_reduction(self) -> Decimal:
        return self.requested - self.recommended_payable


class _Sequence:
    def __init__(self, start: Decimal) -> None:
        self.running = start
        self.items: list[PlannedCorrection] = []

    def add(
        self,
        kind: str,
        reduction: Decimal,
        text: str,
        *,
        line_id: str | None = None,
        rule_id: str | None = None,
        evidence: list[str] | None = None,
        explanation: str = "",
        inputs: dict[str, Any] | None = None,
        arrow: tuple[Decimal, Decimal] | None = None,
    ) -> None:
        """`arrow`: the amounts the text shows (a line's amount before and after); the running amount otherwise."""
        before = self.running
        after = before - reduction
        shown = arrow or (before, after)
        self.items.append(
            PlannedCorrection(
                sequence=len(self.items) + 1,
                type=kind,
                line_id=line_id,
                original_amount=before,
                corrected_amount=after,
                difference=reduction,
                calculation_text=f"{text}: {inr(shown[0])} → {inr(shown[1])}",
                calculation={"formula": text, "inputs": {"before": str(before), "after": str(after), **(inputs or {})}},
                policy_rule_id=rule_id,
                evidence_refs=evidence or [],
                amount_type="calculated",
                applied=True,
                explanation=explanation or text,
            )
        )
        self.running = after


def _apply(line: LineData, action: LineAction) -> LineData | None:
    if action.corrected_amount <= 0:
        return None
    quantity = action.corrected_quantity if action.corrected_quantity is not None else line.quantity
    if action.corrected_unit_price is not None:
        price = action.corrected_unit_price
    else:
        price = q2(action.corrected_amount / quantity) if quantity else line.unit_price
    return replace(line, quantity=quantity, unit_price=price, line_amount=action.corrected_amount)


def _line_text(action: LineAction, line: LineData) -> str:
    return action.calculation_text or f'{action.explanation} "{line.service_description}" ({line.line_id})'


def _policy_steps(seq: _Sequence, evaluation: Evaluation, lines: dict[str, LineData]) -> None:
    failed = [r for r in evaluation.results if r.outcome is Outcome.FAIL]
    removed = [r for r in failed if r.check_code in ("C04", "C05") and r.line_id in lines]
    caps = iter(r for r in failed if r.check_code in SUB_LIMIT_CODES)
    for step in evaluation.steps:
        code = step.step_code.split()[0]
        reduction = step.reduction
        if code == "ELIGIBILITY" and reduction > 0:
            seq.add(CorrectionType.SET_PAYABLE_TO_ZERO, reduction, step.explanation)
        elif code == "COVERAGE":
            for result in removed:
                line = lines[result.line_id]  # type: ignore[index]
                kind = (
                    CorrectionType.REMOVE_EXCLUDED_LINE
                    if result.check_code == "C05"
                    else CorrectionType.REMOVE_UNCOVERED_LINE
                )
                seq.add(
                    kind,
                    line.line_amount,
                    f'"{line.service_description}" ({line.line_id}) {result.explanation}',
                    line_id=line.line_id,
                    rule_id=result.policy_rule_id,
                    explanation=result.explanation,
                    arrow=(line.line_amount, ZERO),
                )
        elif code in SUB_LIMIT_CODES:
            result = next(caps, None)
            formula = (result.inputs or {}).get("formula") if result else None
            seq.add(
                CorrectionType.CAP_AT_SUB_LIMIT,
                reduction,
                formula or step.explanation,
                line_id=result.line_id if result else None,
                rule_id=step.policy_rule_id,
                explanation=step.explanation,
            )
        elif code == "C09" and reduction > 0:
            seq.add(
                CorrectionType.APPLY_DEDUCTIBLE,
                reduction,
                f"{inr(step.amount_before)} - {inr(reduction)} deductible",
                explanation=step.explanation,
            )
        elif code == "C10" and reduction > 0:
            seq.add(
                CorrectionType.APPLY_COPAY,
                reduction,
                f"Co-pay on {inr(step.amount_before)} = {inr(reduction)}",
                explanation=step.explanation,
            )
        elif code == "C11" and reduction > 0:
            seq.add(
                CorrectionType.CAP_AT_OVERALL_LIMIT,
                reduction,
                f"Remaining overall limit {inr(step.amount_after)}",
                explanation=step.explanation,
            )


def build_corrections(inputs: CorrectionInputs, payable: Callable[[list[LineData]], Evaluation]) -> CorrectionPlan:
    claim = inputs.claim
    requested = claim.requested_amount
    seq = _Sequence(requested)
    if inputs.stop is not None:
        seq.add(
            CorrectionType.SET_PAYABLE_TO_ZERO,
            requested,
            inputs.stop.explanation,
            evidence=inputs.stop.evidence_refs,
            explanation=inputs.stop.explanation,
        )
        recommended = ZERO
    else:
        lines = {line.line_id: line for line in claim.lines}
        line_total = sum((line.line_amount for line in claim.lines), ZERO)
        if line_total != requested:
            seq.add(
                CorrectionType.ALIGN_TO_LINE_TOTAL,
                requested - line_total,
                f"Requested {inr(requested)}; the line items total {inr(line_total)}",
            )
        corrected = dict(lines)
        for action in inputs.actions:
            if not action.applied or action.line_id not in lines:
                continue
            line = lines[action.line_id]
            reduction = line.line_amount - action.corrected_amount
            seq.add(
                action.type,
                reduction,
                _line_text(action, line),
                line_id=line.line_id,
                evidence=action.evidence_refs,
                explanation=action.explanation,
                inputs={"line_amount": str(line.line_amount), "corrected_line_amount": str(action.corrected_amount)},
                arrow=(line.line_amount, action.corrected_amount),
            )
            changed = _apply(line, action)
            if changed is None:
                corrected.pop(line.line_id)
            else:
                corrected[line.line_id] = changed
        evaluation = payable(list(corrected.values()))
        _policy_steps(seq, evaluation, corrected)
        recommended = evaluation.payable
    applied = sum((c.difference for c in seq.items), ZERO)
    if requested - applied != recommended:
        raise ReconciliationError(
            f"{claim.claim_id}: requested {requested} - corrections {applied} != recommended payable {recommended}"
        )
    plan = CorrectionPlan(requested, recommended, list(seq.items), inputs.paid)
    for action in inputs.actions:
        if action.applied:
            continue
        line = next((x for x in claim.lines if x.line_id == action.line_id), None)
        amount = (line.line_amount - action.corrected_amount) if line else (action.amount or ZERO)
        corrected_amount = max(ZERO, recommended - amount)
        plan.corrections.append(
            PlannedCorrection(
                sequence=len(plan.corrections) + 1,
                type=action.type,
                line_id=action.line_id,
                original_amount=recommended,
                corrected_amount=corrected_amount,
                difference=amount,
                calculation_text=f"{_line_text(action, line) if line else action.explanation}: for review, not applied",
                calculation={"formula": action.explanation, "inputs": {"amount": str(amount)}},
                policy_rule_id=None,
                evidence_refs=action.evidence_refs,
                amount_type=action.amount_type,
                applied=False,
                explanation=action.explanation,
            )
        )
    if inputs.paid is not None:
        ceiling = min(recommended, inputs.approved) if inputs.approved is not None else recommended
        recovery = inputs.paid - ceiling
        if recovery > 0:
            plan.recovery_amount = recovery
            text = f"Paid {inr(inputs.paid)} - recommended {inr(ceiling)} = {inr(recovery)} recoverable"
            plan.corrections.append(
                PlannedCorrection(
                    len(plan.corrections) + 1,
                    CorrectionType.RECOVER_OVERPAYMENT,
                    None,
                    inputs.paid,
                    ceiling,
                    recovery,
                    text,
                    {"formula": text, "inputs": {"paid": str(inputs.paid)}},
                    None,
                    inputs.settlement_refs,
                    "calculated",
                    True,
                    text,
                )
            )
    return plan
