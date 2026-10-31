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
    # Cross-claim correlation (app/graph/alerts.py) and document comparison.
    CROSS_POLICY_INVOICE_REUSE = "CROSS_POLICY_INVOICE_REUSE"
    INCIDENT_CLAIMED_TWICE = "INCIDENT_CLAIMED_TWICE"
    CONCURRENT_STAYS = "CONCURRENT_STAYS"
    DOCUMENT_REUSED = "DOCUMENT_REUSED"
    DOCUMENT_DISCREPANCY = "DOCUMENT_DISCREPANCY"


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


class ParseStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class NodeType(StrEnum):
    CLAIM = "claim"
    POLICY = "policy"
    CLAIMANT = "claimant"
    PROVIDER = "provider"
    INVOICE = "invoice"
    INCIDENT = "incident"
    DOCUMENT = "document"


class EdgeStrength(StrEnum):
    STRUCTURAL = "structural"
    STRONG = "strong"
    WEAK = "weak"


class GroupTag(StrEnum):
    INVOICE_REUSED_ACROSS_POLICIES = "INVOICE_REUSED_ACROSS_POLICIES"
    INCIDENT_CLAIMED_TWICE = "INCIDENT_CLAIMED_TWICE"
    CONCURRENT_STAYS = "CONCURRENT_STAYS"
    DOCUMENT_REUSED = "DOCUMENT_REUSED"
    DUPLICATE_CLUSTER = "DUPLICATE_CLUSTER"
    WEAK_PATTERN = "WEAK_PATTERN"


class ActorType(StrEnum):
    SYSTEM = "system"
    AI = "ai"


class EventType(StrEnum):
    EXTRACTION_CREATED = "extraction_created"
    COMPARISON_CREATED = "comparison_created"
    GRAPH_BUILT = "graph_built"
    GROUP_CREATED = "group_created"
    CORRECTION_SET_CREATED = "correction_set_created"
    CROSS_CLAIM_ALERT_RAISED = "cross_claim_alert_raised"


class DocType(StrEnum):
    INVOICE = "invoice"
    DISCHARGE_SUMMARY = "discharge_summary"
    REPAIR_ESTIMATE = "repair_estimate"
    OTHER = "other"


class ExtractionStatus(StrEnum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class ProvenanceStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    PAGE_ONLY = "page_only"


class GeneratedBy(StrEnum):
    RULE = "rule"
    AI = "ai"
