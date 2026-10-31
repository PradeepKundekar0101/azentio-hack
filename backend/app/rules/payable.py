"""Payable calculator: eligibility → coverage and exclusions → sub-limits → deductible → co-pay → overall limit,
recording every check and every step from requested to payable."""

from collections.abc import Iterable
from decimal import Decimal

from app.core.enums import ClaimStatus, DeductibleBasis, LimitBasis, Outcome, RuleType
from app.core.money import inr
from app.rules import checks
from app.rules.context import (
    ZERO,
    ClaimContext,
    ClaimData,
    Evaluation,
    LineData,
    PolicyData,
    PolicyLedger,
    Result,
    RuleData,
    Step,
)

RULES_VERSION = "2026.10.1"


def _take(allowed: dict[str, Decimal], lines: list[LineData], amount: Decimal) -> None:
    """Remove `amount` from the in-scope lines' payable amounts, in line order."""
    for line in lines:
        if amount <= 0:
            return
        cut = min(allowed[line.line_id], amount)
        allowed[line.line_id] -= cut
        amount -= cut


def _not_applicable(codes: Iterable[str], reason: str) -> list[Result]:
    return [checks.na(code, reason) for code in codes]


def evaluate(ctx: ClaimContext) -> Evaluation:
    """Evaluate one claim and update the policy ledger in ctx (claims must arrive in incident-date order)."""
    claim, ledger = ctx.claim, ctx.ledger
    results: list[Result] = []
    steps: list[Step] = []

    # 1. Eligibility
    eligibility: list[Result] = []
    for check in (checks.benefit_period, checks.insured_member, checks.claim_type_covered):
        eligibility.append(check(ctx, any(r.outcome is Outcome.FAIL for r in eligibility)))
    results.extend(eligibility)
    failed = [r for r in eligibility if r.outcome is Outcome.FAIL]
    if failed:
        steps.append(Step("ELIGIBILITY", claim.requested_amount, ZERO, f"Not eligible: {failed[0].explanation}"))
        results.extend(
            _not_applicable(("C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11"), "The claim is not eligible.")
        )
        in_period = eligibility[0].outcome is not Outcome.FAIL
        if in_period and claim.status == ClaimStatus.SETTLED.value and claim.settlement:
            ledger.overall_used += claim.settlement.paid_amount
        results.append(checks.settlement_check(ctx, ZERO, {}))
        return Evaluation(claim.claim_id, results, steps, ZERO)
    steps.append(
        Step(
            "ELIGIBILITY",
            claim.requested_amount,
            claim.requested_amount,
            "Eligible: within the benefit period, insured member, claim type covered.",
        )
    )

    # The line items drive the calculation; record any gap between the requested amount and their total.
    amount = claim.requested_amount
    if claim.lines:
        line_total = sum((ln.line_amount for ln in claim.lines), ZERO)
        if line_total != amount:
            steps.append(
                Step("LINE_TOTAL", amount, line_total, f"Requested {inr(amount)}; line items total {inr(line_total)}.")
            )
            amount = line_total

    # 2. Coverage and exclusions per line
    allowed: dict[str, Decimal] = {}
    for line in claim.lines:
        c04, c05 = checks.line_coverage(ctx, line)
        results.extend((c04, c05))
        if c04.outcome is not Outcome.FAIL and c05.outcome is not Outcome.FAIL:
            allowed[line.line_id] = line.line_amount
    covered = sum(allowed.values(), ZERO)
    if claim.lines:
        removed = amount - covered
        steps.append(
            Step(
                "COVERAGE",
                amount,
                covered,
                "Uncovered and excluded lines removed." if removed else "All lines are covered and none is excluded.",
            )
        )
        amount = covered

    # 3. Sub-limits, in the order per day, per claim, per period
    any_sub_limit = False
    for check, code in (
        (checks.per_day_limits, "C06"),
        (checks.per_claim_limits, "C07"),
        (checks.per_period_limits, "C08"),
    ):
        evaluated = check(ctx, allowed)
        if not evaluated:
            results.append(checks.na(code, "The policy has no sub-limit of this kind."))
        for item in evaluated:
            results.append(item.result)
            if item.result.outcome is Outcome.FAIL:
                any_sub_limit = True
                _take(allowed, item.lines, item.result.amount_impact)
                after = amount - item.result.amount_impact
                steps.append(
                    Step(
                        f"{code} {checks.CHECKS[code]}",
                        amount,
                        after,
                        item.result.explanation,
                        item.result.policy_rule_id,
                    )
                )
                amount = after
    for rule in ctx.rules_of(RuleType.SUB_LIMIT.value):
        if rule.limit_basis == LimitBasis.PER_PERIOD.value:
            ledger.sub_limit_used[rule.rule_id] += sum(
                (
                    allowed[ln.line_id]
                    for ln in claim.lines
                    if ln.line_id in allowed and checks.line_in_scope(rule, ln, claim.claim_type)
                ),
                ZERO,
            )
    if not any_sub_limit:
        steps.append(Step("SUB_LIMITS", amount, amount, "No sub-limit exceeded."))

    # 4. Deductible, 5. Co-pay
    c09 = checks.deductible(ctx, amount)
    results.append(c09)
    steps.append(Step("C09 DEDUCTIBLE", amount, amount - c09.amount_impact, c09.explanation))
    amount -= c09.amount_impact
    if ctx.policy.deductible_basis == DeductibleBasis.PER_PERIOD.value:
        ledger.deductible_used += c09.amount_impact
    c10 = checks.copay(ctx, amount)
    results.append(c10)
    steps.append(Step("C10 COPAY", amount, amount - c10.amount_impact, c10.explanation))
    amount -= c10.amount_impact

    # 6. Overall limit
    c11 = checks.overall_limit(ctx, amount)
    results.append(c11)
    steps.append(Step("C11 OVERALL_LIMIT", amount, amount - c11.amount_impact, c11.explanation))
    payable = amount - c11.amount_impact

    settled = claim.status == ClaimStatus.SETTLED.value and claim.settlement is not None
    ledger.overall_used += claim.settlement.paid_amount if settled and claim.settlement else payable
    adjustments = {"deductible": c09.amount_impact, "co-pay": c10.amount_impact}
    results.append(checks.settlement_check(ctx, payable, adjustments))
    return Evaluation(claim.claim_id, results, steps, payable)


def evaluate_policy(policy: PolicyData, rules: tuple[RuleData, ...], claims: Iterable[ClaimData]) -> list[Evaluation]:
    """Evaluate every claim of one policy in incident-date order, sharing the benefit-period ledger."""
    ledger = PolicyLedger()
    ordered = sorted(claims, key=lambda c: (c.incident_date, c.submission_date, c.claim_id))
    return [evaluate(ClaimContext(claim, policy, rules, ledger)) for claim in ordered]
