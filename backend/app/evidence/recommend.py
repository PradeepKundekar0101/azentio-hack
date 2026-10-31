"""The system's recommended correction for each finding.

Until a dedicated corrections module exists, the recommendation is read straight from the alert: the rules
engine already worked out the amount, the formula and the policy rule. This module only names the action
and states the original and corrected amounts, so the evidence history can show what an analyst changed.
"""

from decimal import Decimal
from typing import Any

from app.core.enums import AlertCategory
from app.db.models import Alert, Claim, LineItem, Settlement

ACTIONS: dict[str, str] = {
    AlertCategory.NOT_COVERED: "Remove the amount the policy does not cover",
    AlertCategory.OUT_OF_BENEFIT_PERIOD: "Decline: the incident is outside the benefit period",
    AlertCategory.EXCLUDED_SERVICE: "Remove the excluded service",
    AlertCategory.SUB_LIMIT_EXCEEDED: "Cap the charge at the sub-limit",
    AlertCategory.OVERALL_LIMIT_EXCEEDED: "Cap the payable at the remaining overall limit",
    AlertCategory.SETTLEMENT_OVERPAYMENT: "Recover the overpaid amount",
    AlertCategory.EXACT_DUPLICATE_CLAIM: "Decline the duplicate claim",
    AlertCategory.DUPLICATE_LINE_ITEM: "Remove the duplicate line",
    AlertCategory.NEAR_DUPLICATE: "Hold the overlapping amount until it is checked against the matched claim",
    AlertCategory.EXCESS_FREQUENCY: "Check the frequency of this service before paying",
}


def finding_key(alert: Alert) -> str:
    """The alert's stable finding ID (`ALR-...`): the same finding keeps it across runs, which rebuild alerts
    with new row IDs."""
    return alert.finding_id


def recommendation(
    alert: Alert, claim: Claim, lines: dict[str, LineItem], settlement: Settlement | None
) -> dict[str, Any]:
    """Original amount, the correction, the corrected amount and where they come from."""
    if alert.category == AlertCategory.SETTLEMENT_OVERPAYMENT and settlement is not None:
        original, basis = settlement.paid_amount, f"Paid on settlement {settlement.settlement_id}"
    elif alert.line_id and alert.line_id in lines:
        line = lines[alert.line_id]
        original, basis = line.line_amount, f"Line {line.line_id}: {line.service_description}"
    else:
        original, basis = claim.requested_amount, f"Requested on claim {claim.claim_id}"
    correction = alert.amount
    corrected = None if correction is None else max(Decimal("0"), original - correction)
    return {
        "action": ACTIONS.get(alert.category, "Review this finding"),
        "basis": basis,
        "original_amount": original,
        "correction": correction,
        "corrected_amount": corrected,
        "amount_type": alert.amount_type,
        "calculation": alert.calculation,
        "rule_or_pattern": alert.rule_or_pattern,
        "policy_rule_id": alert.policy_rule_id,
        "source": "rules_engine",
    }


def finding(alert: Alert, claim: Claim, lines: dict[str, LineItem], settlement: Settlement | None) -> dict[str, Any]:
    """A finding as frozen into the evidence history."""
    return {
        "key": finding_key(alert),
        "alert_id": alert.id,
        "category": alert.category,
        "severity": alert.severity,
        "line_id": alert.line_id,
        "amount": alert.amount,
        "amount_type": alert.amount_type,
        "calculation": alert.calculation,
        "rule_or_pattern": alert.rule_or_pattern,
        "policy_rule_id": alert.policy_rule_id,
        "explanation": alert.explanation,
        "status": alert.status,
        "recommendation": recommendation(alert, claim, lines, settlement),
    }
