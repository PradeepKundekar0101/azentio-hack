"""Checks C01-C12. Each is a pure function of the claim context (and the running amounts) returning results."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.core.enums import Category, ClaimStatus, DeductibleBasis, LimitBasis, Outcome, RuleType, ScopeType
from app.core.money import inr, q2
from app.rules import explain
from app.rules.context import ZERO, ClaimContext, LineData, Result, RuleData

# Codes and readable names; the registry order is the order checks are evaluated and shown.
CHECKS = {
    "C01": "BENEFIT_PERIOD",
    "C02": "INSURED_MEMBER",
    "C03": "CLAIM_TYPE_COVERED",
    "C04": "LINE_COVERED",
    "C05": "EXCLUSION",
    "C06": "SUB_LIMIT_PER_DAY",
    "C07": "SUB_LIMIT_PER_CLAIM",
    "C08": "SUB_LIMIT_PER_PERIOD",
    "C09": "DEDUCTIBLE",
    "C10": "COPAY",
    "C11": "OVERALL_LIMIT",
    "C12": "SETTLEMENT_CHECK",
}

DAILY_CATEGORIES = {Category.ROOM.value, Category.ICU.value}


def na(code: str, reason: str, line_id: str | None = None) -> Result:
    return Result(code, Outcome.NOT_APPLICABLE, reason, line_id=line_id)


def na_rule(code: str, rule: RuleData) -> Result:
    return Result(code, Outcome.NOT_APPLICABLE, f"No lines in scope of {rule.label}.", policy_rule_id=rule.rule_id)


def line_in_scope(rule: RuleData, line: LineData, claim_type: str) -> bool:
    if rule.scope_type == ScopeType.CATEGORY.value:
        return line.category == rule.scope_value
    if rule.scope_type == ScopeType.SERVICE_CODE.value:
        return line.service_code == rule.scope_value
    return rule.scope_type == ScopeType.CLAIM_TYPE.value and claim_type == rule.scope_value


# Eligibility (claim level). The first failing check carries the full requested amount; later eligibility
# failures are recorded with no further amount, so the claim's leakage is never counted twice.


def benefit_period(ctx: ClaimContext, already_failed: bool) -> Result:
    claim, policy = ctx.claim, ctx.policy
    inputs = {
        "incident_date": claim.incident_date.isoformat(),
        "benefit_period_start": policy.benefit_period_start.isoformat(),
        "benefit_period_end": policy.benefit_period_end.isoformat(),
    }
    expected = f"{explain.d(policy.benefit_period_start)} to {explain.d(policy.benefit_period_end)}"
    if policy.benefit_period_start <= claim.incident_date <= policy.benefit_period_end:
        return Result(
            "C01",
            Outcome.PASS,
            f"Incident on {explain.d(claim.incident_date)} is within the benefit period {expected}.",
            expected=expected,
            actual=explain.d(claim.incident_date),
            inputs=inputs,
        )
    amount = ZERO if already_failed else claim.requested_amount
    return Result(
        "C01",
        Outcome.FAIL,
        f"Incident on {explain.d(claim.incident_date)} is outside the benefit period {expected}, "
        f"so the requested {inr(claim.requested_amount)} is not payable.",
        amount_impact=amount,
        expected=expected,
        actual=explain.d(claim.incident_date),
        inputs=inputs,
    )


def insured_member(ctx: ClaimContext, already_failed: bool) -> Result:
    claim, policy = ctx.claim, ctx.policy
    members = ", ".join(policy.insured_member_ids)
    inputs = {"claimant_id": claim.claimant_id, "insured_member_ids": list(policy.insured_member_ids)}
    if claim.claimant_id in policy.insured_member_ids:
        return Result(
            "C02",
            Outcome.PASS,
            f"Claimant {claim.claimant_id} is insured under {policy.policy_number}.",
            expected=members,
            actual=claim.claimant_id,
            inputs=inputs,
        )
    return Result(
        "C02",
        Outcome.FAIL,
        f"Claimant {claim.claimant_id} is not an insured member of {policy.policy_number} (members: {members}), "
        f"so the requested {inr(claim.requested_amount)} is not covered.",
        amount_impact=ZERO if already_failed else claim.requested_amount,
        expected=members,
        actual=claim.claimant_id,
        inputs=inputs,
    )


def claim_type_covered(ctx: ClaimContext, already_failed: bool) -> Result:
    claim = ctx.claim
    coverage = next(
        (
            r
            for r in ctx.rules_of(RuleType.COVERAGE.value)
            if r.scope_type == ScopeType.CLAIM_TYPE.value and r.scope_value == claim.claim_type
        ),
        None,
    )
    if coverage:
        return Result(
            "C03",
            Outcome.PASS,
            f"{claim.claim_type.capitalize()} claims are covered ({coverage.label}).",
            policy_rule_id=coverage.rule_id,
            expected="coverage rule for claim type",
            actual=claim.claim_type,
        )
    return Result(
        "C03",
        Outcome.FAIL,
        f"The policy has no coverage rule for {claim.claim_type} claims, "
        f"so the requested {inr(claim.requested_amount)} is not covered.",
        amount_impact=ZERO if already_failed else claim.requested_amount,
        expected="coverage rule for claim type",
        actual=claim.claim_type,
    )


# Lines


def line_coverage(ctx: ClaimContext, line: LineData) -> tuple[Result, Result]:
    """C04 coverage and C05 exclusion for one line. C05 is not applicable when the line is not covered."""
    coverage = next(
        (
            r
            for r in ctx.rules_of(RuleType.COVERAGE.value)
            if r.scope_type in (ScopeType.CATEGORY.value, ScopeType.SERVICE_CODE.value)
            and line_in_scope(r, line, ctx.claim.claim_type)
        ),
        None,
    )
    what = f"{line.service_description} ({line.service_code}, {line.category})"
    if coverage is None:
        c04 = Result(
            "C04",
            Outcome.FAIL,
            f"{what} has no coverage rule, so the line amount {inr(line.line_amount)} is not covered.",
            amount_impact=line.line_amount,
            line_id=line.line_id,
            expected="coverage rule for category or service code",
            actual=f"{line.category} / {line.service_code}",
        )
        return c04, na("C05", "Line is not covered, so exclusions do not apply.", line.line_id)
    c04 = Result(
        "C04",
        Outcome.PASS,
        f"{what} is covered ({coverage.label}).",
        line_id=line.line_id,
        policy_rule_id=coverage.rule_id,
    )
    exclusion = next(
        (r for r in ctx.rules_of(RuleType.EXCLUSION.value) if line_in_scope(r, line, ctx.claim.claim_type)),
        None,
    )
    if exclusion is None:
        return c04, Result("C05", Outcome.PASS, f"{what} matches no exclusion.", line_id=line.line_id)
    c05 = Result(
        "C05",
        Outcome.FAIL,
        f"{what} is excluded ({exclusion.label}), so the line amount {inr(line.line_amount)} is not payable.",
        amount_impact=line.line_amount,
        line_id=line.line_id,
        policy_rule_id=exclusion.rule_id,
        expected=f"not {exclusion.scope_value}",
        actual=line.service_code,
    )
    return c04, c05


# Sub-limits. `allowed` maps line_id -> amount still payable for that line, and is reduced in place by evaluate().


@dataclass
class Excess:
    result: Result
    lines: list[LineData]  # in-scope lines the excess is taken from


def _scoped(ctx: ClaimContext, rule: RuleData, allowed: dict[str, Decimal]) -> list[LineData]:
    return [
        line for line in ctx.claim.lines if line.line_id in allowed and line_in_scope(rule, line, ctx.claim.claim_type)
    ]


def per_day_limits(ctx: ClaimContext, allowed: dict[str, Decimal]) -> list[Excess]:
    out: list[Excess] = []
    rules = [r for r in ctx.rules_of(RuleType.SUB_LIMIT.value) if r.limit_basis == LimitBasis.PER_DAY.value]
    for rule in rules:
        limit = rule.limit_amount or ZERO
        by_date: dict = defaultdict(list)
        for line in _scoped(ctx, rule, allowed):
            by_date[line.service_date].append(line)
        if not by_date:
            out.append(Excess(na_rule("C06", rule), []))
            continue
        for service_date, lines in sorted(by_date.items()):
            # Room and ICU quantities are days, so the daily rate is the unit price; other lines count once.
            count = max((ln.quantity if ln.category in DAILY_CATEGORIES else Decimal(1)) for ln in lines)
            rate = q2(sum((ln.line_amount / (ln.quantity if ln.category in DAILY_CATEGORIES else 1)) for ln in lines))
            excess = q2(max(ZERO, rate - limit) * count)
            first = lines[0]
            what = explain.scope_name(rule).capitalize()
            inputs = {
                "service_date": service_date.isoformat(),
                "daily_rate": str(rate),
                "days": str(count),
                "limit_per_day": str(limit),
                "line_ids": [ln.line_id for ln in lines],
            }
            if excess > 0:
                result = Result(
                    "C06",
                    Outcome.FAIL,
                    explain.per_day_excess(rule, rate, count, excess, what),
                    amount_impact=excess,
                    line_id=first.line_id,
                    policy_rule_id=rule.rule_id,
                    expected=f"≤ {inr(limit)}/day",
                    actual=f"{inr(rate)}/day × {explain.days(count)}",
                    inputs=inputs | {"formula": explain.per_day_formula(rule, rate, count, excess)},
                )
            else:
                result = Result(
                    "C06",
                    Outcome.PASS,
                    f"{what} {inr(rate)}/day is within the {inr(limit)}/day limit ({rule.label}).",
                    line_id=first.line_id,
                    policy_rule_id=rule.rule_id,
                    expected=f"≤ {inr(limit)}/day",
                    actual=f"{inr(rate)}/day",
                    inputs=inputs,
                )
            out.append(Excess(result, lines))
    return out


def per_claim_limits(ctx: ClaimContext, allowed: dict[str, Decimal]) -> list[Excess]:
    out: list[Excess] = []
    rules = [r for r in ctx.rules_of(RuleType.SUB_LIMIT.value) if r.limit_basis == LimitBasis.PER_CLAIM.value]
    for rule in rules:
        lines = _scoped(ctx, rule, allowed)
        limit = rule.limit_amount or ZERO
        if not lines:
            out.append(Excess(na_rule("C07", rule), []))
            continue
        total = q2(sum(allowed[ln.line_id] for ln in lines))
        excess = max(ZERO, total - limit)
        name = explain.scope_name(rule)
        inputs = {"in_scope_total": str(total), "limit": str(limit), "line_ids": [ln.line_id for ln in lines]}
        if excess > 0:
            result = Result(
                "C07",
                Outcome.FAIL,
                f"{name.capitalize()} charges of {inr(total)} exceed the {inr(limit)} per-claim limit ({rule.label}): "
                f"{inr(total)} − {inr(limit)} = {inr(excess)}.",
                amount_impact=excess,
                policy_rule_id=rule.rule_id,
                expected=f"≤ {inr(limit)} per claim",
                actual=inr(total),
                inputs=inputs | {"formula": f"{inr(total)} − {inr(limit)} = {inr(excess)}"},
            )
        else:
            result = Result(
                "C07",
                Outcome.PASS,
                f"{name.capitalize()} charges of {inr(total)} are within the {inr(limit)} per-claim limit "
                f"({rule.label}).",
                policy_rule_id=rule.rule_id,
                expected=f"≤ {inr(limit)} per claim",
                actual=inr(total),
                inputs=inputs,
            )
        out.append(Excess(result, lines))
    return out


def per_period_limits(ctx: ClaimContext, allowed: dict[str, Decimal]) -> list[Excess]:
    out: list[Excess] = []
    rules = [r for r in ctx.rules_of(RuleType.SUB_LIMIT.value) if r.limit_basis == LimitBasis.PER_PERIOD.value]
    for rule in rules:
        lines = _scoped(ctx, rule, allowed)
        limit = rule.limit_amount or ZERO
        used = ctx.ledger.sub_limit_used[rule.rule_id]
        remaining = max(ZERO, limit - used)
        if not lines:
            out.append(Excess(na_rule("C08", rule), []))
            continue
        total = q2(sum(allowed[ln.line_id] for ln in lines))
        excess = max(ZERO, total - remaining)
        name = explain.scope_name(rule)
        inputs = {
            "in_scope_total": str(total),
            "limit": str(limit),
            "used_by_earlier_claims": str(used),
            "remaining": str(remaining),
            "line_ids": [ln.line_id for ln in lines],
        }
        if excess > 0:
            result = Result(
                "C08",
                Outcome.FAIL,
                f"{name.capitalize()} charges of {inr(total)} exceed the {inr(remaining)} left of the {inr(limit)} "
                f"per-period limit ({rule.label}; {inr(used)} used by earlier claims): "
                f"{inr(total)} − {inr(remaining)} = {inr(excess)}.",
                amount_impact=excess,
                policy_rule_id=rule.rule_id,
                expected=f"≤ {inr(remaining)} remaining",
                actual=inr(total),
                inputs=inputs | {"formula": f"{inr(total)} − {inr(remaining)} = {inr(excess)}"},
            )
        else:
            result = Result(
                "C08",
                Outcome.PASS,
                f"{name.capitalize()} charges of {inr(total)} are within the {inr(remaining)} left of the "
                f"{inr(limit)} per-period limit ({rule.label}).",
                policy_rule_id=rule.rule_id,
                expected=f"≤ {inr(remaining)} remaining",
                actual=inr(total),
                inputs=inputs,
            )
        out.append(Excess(result, lines))
    return out


# Member's share and limits (claim level)


def deductible(ctx: ClaimContext, amount: Decimal) -> Result:
    policy = ctx.policy
    if policy.deductible_amount == 0:
        return na("C09", "The policy has no deductible.")
    if policy.deductible_basis == DeductibleBasis.PER_PERIOD.value:
        remaining = max(ZERO, policy.deductible_amount - ctx.ledger.deductible_used)
        basis = (
            f"{inr(remaining)} left of the {inr(policy.deductible_amount)} per-period deductible "
            f"({inr(ctx.ledger.deductible_used)} applied to earlier claims)"
        )
    else:
        remaining = policy.deductible_amount
        basis = f"the {inr(policy.deductible_amount)} per-claim deductible"
    applied = min(remaining, amount)
    inputs = {"amount_before": str(amount), "deductible_remaining": str(remaining), "basis": policy.deductible_basis}
    if applied == 0:
        return Result("C09", Outcome.PASS, f"No deductible left to apply ({basis}).", inputs=inputs)
    return Result(
        "C09",
        Outcome.ADJUSTED,
        f"Deductible of {inr(applied)} applied from {basis}.",
        amount_impact=applied,
        expected=inr(applied),
        actual=inr(applied),
        inputs=inputs,
    )


def copay(ctx: ClaimContext, amount: Decimal) -> Result:
    percent = ctx.policy.copay_percent
    if percent == 0:
        return na("C10", "The policy has no co-pay.")
    share = q2(amount * percent / 100)
    pct = explain.qty(percent)
    return Result(
        "C10",
        Outcome.ADJUSTED if share > 0 else Outcome.PASS,
        f"Co-pay of {pct}% on {inr(amount)} = {inr(share)} is the member's share.",
        amount_impact=share,
        expected=inr(share),
        actual=inr(share),
        inputs={
            "amount_after_deductible": str(amount),
            "copay_percent": str(percent),
            "formula": f"{pct}% × {inr(amount)} = {inr(share)}",
        },
    )


def overall_limit(ctx: ClaimContext, payable: Decimal) -> Result:
    policy, used = ctx.policy, ctx.ledger.overall_used
    remaining = max(ZERO, policy.overall_limit - used)
    excess = max(ZERO, payable - remaining)
    inputs = {
        "payable": str(payable),
        "overall_limit": str(policy.overall_limit),
        "used_by_earlier_claims": str(used),
        "remaining": str(remaining),
    }
    if excess == 0:
        return Result(
            "C11",
            Outcome.PASS,
            f"Payable {inr(payable)} is within the {inr(remaining)} left of the "
            f"{inr(policy.overall_limit)} overall limit.",
            expected=f"≤ {inr(remaining)}",
            actual=inr(payable),
            inputs=inputs,
        )
    return Result(
        "C11",
        Outcome.FAIL,
        f"Payable {inr(payable)} exceeds the {inr(remaining)} left of the {inr(policy.overall_limit)} overall limit "
        f"({inr(used)} already used by earlier claims): {inr(payable)} − {inr(remaining)} = {inr(excess)}.",
        amount_impact=excess,
        expected=f"≤ {inr(remaining)}",
        actual=inr(payable),
        inputs=inputs | {"formula": f"{inr(payable)} − {inr(remaining)} = {inr(excess)}"},
    )


def settlement_check(ctx: ClaimContext, entitlement: Decimal, adjustments: dict[str, Decimal]) -> Result:
    claim = ctx.claim
    settlement = claim.settlement
    if claim.status != ClaimStatus.SETTLED.value or settlement is None:
        return na("C12", "Only settled claims with a settlement record are compared with what was paid.")
    paid, approved = settlement.paid_amount, settlement.approved_amount
    ceiling = min(entitlement, approved)
    overpaid = max(ZERO, paid - ceiling)
    inputs = {
        "settlement_id": settlement.settlement_id,
        "paid": str(paid),
        "approved": str(approved),
        "entitlement": str(entitlement),
    }
    if overpaid == 0:
        return Result(
            "C12",
            Outcome.PASS,
            f"Paid {inr(paid)} is within the approved {inr(approved)} and the recomputed "
            f"entitlement {inr(entitlement)}.",
            expected=f"≤ {inr(ceiling)}",
            actual=inr(paid),
            inputs=inputs,
        )
    reasons = []
    for name, amount in adjustments.items():
        if amount > 0 and abs(overpaid - amount) <= Decimal("1.00"):
            reasons.append(f"{name} of {inr(amount)} not applied")
    if paid > approved:
        reasons.append(f"paid {inr(paid - approved)} above the approved {inr(approved)}")
    why = "; ".join(reasons) if reasons else "the policy terms reduce the payable amount"
    return Result(
        "C12",
        Outcome.FAIL,
        f"Paid {inr(paid)}; entitlement {inr(entitlement)}; {why}. Overpayment: "
        f"{inr(paid)} − {inr(ceiling)} = {inr(overpaid)}.",
        amount_impact=overpaid,
        expected=f"≤ {inr(ceiling)}",
        actual=inr(paid),
        inputs=inputs | {"reasons": reasons, "formula": f"{inr(paid)} − {inr(ceiling)} = {inr(overpaid)}"},
    )
