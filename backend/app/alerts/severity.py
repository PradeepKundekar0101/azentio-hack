"""Alert severity: by category, raised by the calculated amount; the higher of the two wins."""

from decimal import Decimal

from app.core.config import Settings
from app.core.enums import AlertCategory, AmountType, Severity

RANK = {Severity.REVIEW: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}

BY_CATEGORY = {
    AlertCategory.EXACT_DUPLICATE_CLAIM: Severity.CRITICAL,
    AlertCategory.NOT_COVERED: Severity.HIGH,
    AlertCategory.OUT_OF_BENEFIT_PERIOD: Severity.HIGH,
    AlertCategory.EXCLUDED_SERVICE: Severity.HIGH,
    AlertCategory.OVERALL_LIMIT_EXCEEDED: Severity.HIGH,
    AlertCategory.SETTLEMENT_OVERPAYMENT: Severity.HIGH,
    AlertCategory.SUB_LIMIT_EXCEEDED: Severity.MEDIUM,
    AlertCategory.DUPLICATE_LINE_ITEM: Severity.MEDIUM,
    AlertCategory.NEAR_DUPLICATE: Severity.REVIEW,
    AlertCategory.EXCESS_FREQUENCY: Severity.REVIEW,
    AlertCategory.CROSS_POLICY_INVOICE_REUSE: Severity.CRITICAL,
    AlertCategory.DOCUMENT_REUSED: Severity.CRITICAL,
    AlertCategory.INCIDENT_CLAIMED_TWICE: Severity.REVIEW,
    AlertCategory.CONCURRENT_STAYS: Severity.REVIEW,
    AlertCategory.DOCUMENT_DISCREPANCY: Severity.MEDIUM,
}


def by_amount(amount: Decimal, settings: Settings) -> Severity:
    if amount >= settings.severity_critical_amount:
        return Severity.CRITICAL
    if amount >= settings.severity_high_amount:
        return Severity.HIGH
    if amount >= settings.severity_medium_amount:
        return Severity.MEDIUM
    return Severity.LOW


def severity(category: AlertCategory, amount_type: AmountType, amount: Decimal | None, settings: Settings) -> Severity:
    base = BY_CATEGORY[category]
    if amount_type is not AmountType.CALCULATED or amount is None:
        return base
    from_amount = by_amount(amount, settings)
    return max(base, from_amount, key=RANK.__getitem__)
