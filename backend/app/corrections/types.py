"""Correction types: what each one does and what supports it."""

from enum import StrEnum


class CorrectionType(StrEnum):
    SET_PAYABLE_TO_ZERO = "SET_PAYABLE_TO_ZERO"
    ALIGN_TO_LINE_TOTAL = "ALIGN_TO_LINE_TOTAL"
    REMOVE_DUPLICATE_LINE = "REMOVE_DUPLICATE_LINE"
    REMOVE_UNSUPPORTED_LINE = "REMOVE_UNSUPPORTED_LINE"
    ADJUST_TO_DOCUMENT = "ADJUST_TO_DOCUMENT"
    REDUCE_ROOM_DAYS = "REDUCE_ROOM_DAYS"
    REMOVE_EXCLUDED_LINE = "REMOVE_EXCLUDED_LINE"
    REMOVE_UNCOVERED_LINE = "REMOVE_UNCOVERED_LINE"
    CAP_AT_SUB_LIMIT = "CAP_AT_SUB_LIMIT"
    APPLY_DEDUCTIBLE = "APPLY_DEDUCTIBLE"
    APPLY_COPAY = "APPLY_COPAY"
    CAP_AT_OVERALL_LIMIT = "CAP_AT_OVERALL_LIMIT"
    RECOVER_OVERPAYMENT = "RECOVER_OVERPAYMENT"


# Line-level corrections in priority order: a line gets at most one, the first that applies.
LINE_PRIORITY = [
    CorrectionType.REMOVE_DUPLICATE_LINE,
    CorrectionType.REMOVE_UNSUPPORTED_LINE,
    CorrectionType.ADJUST_TO_DOCUMENT,
    CorrectionType.REDUCE_ROOM_DAYS,
]

SUPPORT = {
    CorrectionType.SET_PAYABLE_TO_ZERO: "Duplicate, cross-claim alert or failed eligibility",
    CorrectionType.ALIGN_TO_LINE_TOTAL: "Claim line items",
    CorrectionType.REMOVE_DUPLICATE_LINE: "Duplicate match",
    CorrectionType.REMOVE_UNSUPPORTED_LINE: "Document discrepancy",
    CorrectionType.ADJUST_TO_DOCUMENT: "Document discrepancy",
    CorrectionType.REDUCE_ROOM_DAYS: "Document discrepancy",
    CorrectionType.REMOVE_EXCLUDED_LINE: "Policy rule",
    CorrectionType.REMOVE_UNCOVERED_LINE: "Policy rule",
    CorrectionType.CAP_AT_SUB_LIMIT: "Policy rule",
    CorrectionType.APPLY_DEDUCTIBLE: "Policy rule",
    CorrectionType.APPLY_COPAY: "Policy rule",
    CorrectionType.CAP_AT_OVERALL_LIMIT: "Policy rule and settlements",
    CorrectionType.RECOVER_OVERPAYMENT: "Settlement record",
}

# Not part of requested - corrections = recommended payable: it compares the payable with what was already paid.
OUTSIDE_RECONCILIATION = {CorrectionType.RECOVER_OVERPAYMENT}
