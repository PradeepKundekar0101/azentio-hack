"""Turn failed checks and flagged duplicates into alerts: one per finding, with amount type, calculation and links.

Open claims (pre-payment): failed C01-C08 and C11 are leakage if paid as requested. Deductible and co-pay are
normal policy application and only alert when ALERT_ON_ADJUSTMENTS is set.
Settled claims (post-payment): their failed checks are already inside the recomputed entitlement, so the one
alert is the C12 overpayment (paid minus entitlement).
"""

from decimal import Decimal
from typing import Any

from app.alerts.severity import severity
from app.core.config import Settings
from app.core.enums import AlertCategory, AlertStatus, AmountType, ClaimStatus, MatchDecision, MatchType, Outcome
from app.core.money import inr
from app.rules.checks import CHECKS
from app.rules.context import Evaluation, Result

CHECK_CATEGORY = {
    "C01": AlertCategory.OUT_OF_BENEFIT_PERIOD,
    "C02": AlertCategory.NOT_COVERED,
    "C03": AlertCategory.NOT_COVERED,
    "C04": AlertCategory.NOT_COVERED,
    "C05": AlertCategory.EXCLUDED_SERVICE,
    "C06": AlertCategory.SUB_LIMIT_EXCEEDED,
    "C07": AlertCategory.SUB_LIMIT_EXCEEDED,
    "C08": AlertCategory.SUB_LIMIT_EXCEEDED,
    "C11": AlertCategory.OVERALL_LIMIT_EXCEEDED,
    "C12": AlertCategory.SETTLEMENT_OVERPAYMENT,
}
ADJUSTMENT_CHECKS = {"C09", "C10"}

MATCH_CATEGORY = {
    MatchType.EXACT_CLAIM.value: AlertCategory.EXACT_DUPLICATE_CLAIM,
    MatchType.DUPLICATE_LINE.value: AlertCategory.DUPLICATE_LINE_ITEM,
    MatchType.NEAR_DUPLICATE.value: AlertCategory.NEAR_DUPLICATE,
}


def _calculation(result: Result) -> str:
    inputs = result.inputs or {}
    return inputs.get("formula") or f"{inr(result.amount_impact)} ({CHECKS[result.check_code]})"


def _line_ids(result: Result) -> list[str]:
    ids = list((result.inputs or {}).get("line_ids", []))
    if result.line_id and result.line_id not in ids:
        ids.insert(0, result.line_id)
    return ids


def _alert(
    run_id: int,
    claim_id: str,
    category: AlertCategory,
    amount_type: AmountType,
    amount: Decimal | None,
    settings: Settings,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "claim_id": claim_id,
        "category": category.value,
        "severity": severity(category, amount_type, amount, settings).value,
        "amount": amount,
        "amount_type": amount_type.value,
        "status": AlertStatus.OPEN.value,
        **fields,
    }


def alerts_from_results(
    run_id: int, evaluations: list[Evaluation], claims: dict[str, Any], settings: Settings
) -> list[dict[str, Any]]:
    alerts = []
    for evaluation in evaluations:
        claim = claims[evaluation.claim_id]
        settled = claim.status == ClaimStatus.SETTLED.value
        for result in evaluation.results:
            code = result.check_code
            if settled:
                raise_it = code == "C12" and result.outcome is Outcome.FAIL
            elif code in ADJUSTMENT_CHECKS:
                raise_it = settings.alert_on_adjustments and result.outcome is Outcome.ADJUSTED
            else:
                raise_it = code in CHECK_CATEGORY and code != "C12" and result.outcome is Outcome.FAIL
            if not raise_it:
                continue
            category = CHECK_CATEGORY.get(code, AlertCategory.NOT_COVERED)
            line_ids = _line_ids(result)
            supporting = {
                "claim_id": claim.claim_id,
                "policy_number": claim.policy_number,
                "policy_rule_id": result.policy_rule_id,
                "line_ids": line_ids,
                "settlement_id": (result.inputs or {}).get("settlement_id"),
                "validation_result": {"check_code": code, "line_id": result.line_id},
            }
            alerts.append(
                _alert(
                    run_id,
                    claim.claim_id,
                    category,
                    AmountType.CALCULATED,
                    result.amount_impact,
                    settings,
                    line_id=result.line_id,
                    calculation=_calculation(result),
                    rule_or_pattern=f"{code} {CHECKS[code]}",
                    policy_rule_id=result.policy_rule_id,
                    explanation=result.explanation,
                    supporting=supporting,
                )
            )
    return alerts


def alerts_from_matches(
    run_id: int, matches: list[dict[str, Any]], claims: dict[str, Any], lines: dict[str, Any], settings: Settings
) -> list[dict[str, Any]]:
    alerts = []
    for match in matches:
        if match["decision"] != MatchDecision.FLAGGED.value:
            continue
        signals = match.get("signals") or {}
        claim = claims[match["claim_id"]]
        if signals.get("excess_frequency"):
            category, amount_type, amount = AlertCategory.EXCESS_FREQUENCY, AmountType.SUSPECTED, None
            calculation = None
        elif match["match_type"] == MatchType.EXACT_CLAIM.value:
            category, amount_type, amount = (
                AlertCategory.EXACT_DUPLICATE_CLAIM,
                AmountType.CALCULATED,
                claim.requested_amount,
            )
            calculation = f"Requested amount of the repeated claim: {inr(amount)}"
        elif match["match_type"] == MatchType.DUPLICATE_LINE.value:
            amount = lines[match["line_id"]].line_amount
            category, amount_type = AlertCategory.DUPLICATE_LINE_ITEM, AmountType.CALCULATED
            calculation = f"Amount of the repeated line: {inr(amount)}"
        else:
            amount = Decimal(signals["overlapping_amount"])
            category, amount_type = AlertCategory.NEAR_DUPLICATE, AmountType.ESTIMATED
            calculation = f"Overlapping services in the later claim: {inr(amount)} (for review, not deducted)"
        supporting = {
            "claim_id": claim.claim_id,
            "policy_number": claim.policy_number,
            "line_ids": [i for i in (match.get("line_id"),) if i],
            "matched_claim_id": match["matched_claim_id"],
            "matched_line_id": match.get("matched_line_id"),
            "matched_source": match["matched_source"],
            "score": str(match["score"]) if match.get("score") is not None else None,
        }
        alerts.append(
            _alert(
                run_id,
                claim.claim_id,
                category,
                amount_type,
                amount,
                settings,
                line_id=match.get("line_id"),
                calculation=calculation,
                rule_or_pattern=match["match_type"].upper()
                if category is not AlertCategory.EXCESS_FREQUENCY
                else "EXCESS_FREQUENCY",
                policy_rule_id=None,
                explanation=match["reason"],
                supporting=supporting,
            )
        )
    return alerts


def build_alerts(
    run_id: int, loaded: dict[str, Any], evaluations: list[Evaluation], matches: list[dict], settings: Settings
) -> list[dict[str, Any]]:
    claims = {c.claim_id: c for c in loaded["claim_rows"]}
    lines = {ln.line_id: ln for ln in loaded["line_rows"]}
    return alerts_from_results(run_id, evaluations, claims, settings) + alerts_from_matches(
        run_id, matches, claims, lines, settings
    )
