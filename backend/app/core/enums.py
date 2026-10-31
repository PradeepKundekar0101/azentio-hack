"""Closed value sets from the data contracts. Stored as text with CHECK constraints."""

from enum import StrEnum


class ClaimType(StrEnum):
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"
    DAYCARE = "daycare"
    PHARMACY = "pharmacy"
    DIAGNOSTICS = "diagnostics"


class ClaimStatus(StrEnum):
    OPEN = "open"
    SETTLED = "settled"


class ClaimSource(StrEnum):
    FILE = "file"
    DOCUMENT = "document"


class Category(StrEnum):
    ROOM = "room"
    ICU = "icu"
    CONSULTATION = "consultation"
    PROCEDURE = "procedure"
    PHARMACY = "pharmacy"
    DIAGNOSTICS = "diagnostics"
    CONSUMABLES = "consumables"
    PHYSIOTHERAPY = "physiotherapy"
    OTHER = "other"


class DeductibleBasis(StrEnum):
    PER_CLAIM = "per_claim"
    PER_PERIOD = "per_period"


class RuleType(StrEnum):
    COVERAGE = "coverage"
    EXCLUSION = "exclusion"
    SUB_LIMIT = "sub_limit"


class ScopeType(StrEnum):
    CATEGORY = "category"
    SERVICE_CODE = "service_code"
    CLAIM_TYPE = "claim_type"


class LimitBasis(StrEnum):
    PER_DAY = "per_day"
    PER_CLAIM = "per_claim"
    PER_PERIOD = "per_period"


class SettlementStatus(StrEnum):
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    REJECTED = "rejected"


class BatchStatus(StrEnum):
    RECEIVED = "received"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunScope(StrEnum):
    BATCH = "batch"
    ALL = "all"


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    ADJUSTED = "adjusted"


class MatchSource(StrEnum):
    CLAIM = "claim"
    SETTLEMENT = "settlement"


class MatchType(StrEnum):
    EXACT_CLAIM = "exact_claim"
    DUPLICATE_LINE = "duplicate_line"
    NEAR_DUPLICATE = "near_duplicate"
    LEGITIMATE_REPEAT = "legitimate_repeat"


class MatchDecision(StrEnum):
    FLAGGED = "flagged"
    CLEARED = "cleared"


class AlertCategory(StrEnum):
    NOT_COVERED = "NOT_COVERED"
    OUT_OF_BENEFIT_PERIOD = "OUT_OF_BENEFIT_PERIOD"
    EXCLUDED_SERVICE = "EXCLUDED_SERVICE"
    SUB_LIMIT_EXCEEDED = "SUB_LIMIT_EXCEEDED"
    OVERALL_LIMIT_EXCEEDED = "OVERALL_LIMIT_EXCEEDED"
    SETTLEMENT_OVERPAYMENT = "SETTLEMENT_OVERPAYMENT"
    EXACT_DUPLICATE_CLAIM = "EXACT_DUPLICATE_CLAIM"
    DUPLICATE_LINE_ITEM = "DUPLICATE_LINE_ITEM"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    EXCESS_FREQUENCY = "EXCESS_FREQUENCY"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW = "review"


class AmountType(StrEnum):
    CALCULATED = "calculated"
    ESTIMATED = "estimated"
    SUSPECTED = "suspected"


class AlertStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    EVIDENCE_REQUESTED = "evidence_requested"
    ESCALATED = "escalated"


class Role(StrEnum):
    """Who may do what. Analysts review and escalate; senior reviewers decide escalations; admins onboard."""

    ANALYST = "analyst"
    SENIOR_REVIEWER = "senior_reviewer"
    ADMIN = "admin"


class EscalationTarget(StrEnum):
    SENIOR_REVIEWER = "senior_reviewer"
    SIU = "siu"


class ParseStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    FAILED = "failed"
