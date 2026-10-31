"""Field-level contracts per dataset: how each field is parsed and what makes a value invalid.

Row parsing collects every problem in a row instead of stopping at the first one.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from app.core import enums
from app.core.money import AmountError, parse_amount
from app.ingest.mapping import Dataset


class Code(StrEnum):
    MISSING_FIELD = "missing_field"
    MISSING_COLUMN = "missing_column"
    UNKNOWN_COLUMN = "unknown_column"
    UNKNOWN_DATASET = "unknown_dataset"
    UNREADABLE_FILE = "unreadable_file"
    INVALID_FORMAT = "invalid_format"
    INVALID_VALUE = "invalid_value"
    INVALID_AMOUNT = "invalid_amount"
    NEGATIVE_AMOUNT = "negative_amount"
    INVALID_DATE = "invalid_date"
    AMBIGUOUS_DATE = "ambiguous_date"
    FUTURE_DATE = "future_date"
    SUBMISSION_BEFORE_INCIDENT = "submission_before_incident"
    PERIOD_END_BEFORE_START = "period_end_before_start"
    UNKNOWN_POLICY = "unknown_policy"
    UNKNOWN_CLAIM = "unknown_claim"
    CLAIM_NOT_SETTLED = "claim_not_settled"
    SETTLEMENT_BEFORE_SUBMISSION = "settlement_before_submission"
    UNKNOWN_SERVICE_CODE = "unknown_service_code"
    LINE_AMOUNT_MISMATCH = "line_amount_mismatch"
    DUPLICATE_ID_IN_FILE = "duplicate_id_in_file"
    ID_EXISTS = "id_exists"
    PARENT_REJECTED = "parent_rejected"
    # Warnings
    CLAIMANT_NOT_INSURED = "claimant_not_insured"
    REQUESTED_AMOUNT_MISMATCH = "requested_amount_mismatch"
    SERVICE_DATE_FAR = "service_date_far"
    PAID_ABOVE_APPROVED = "paid_above_approved"


@dataclass
class FieldIssue:
    field: str
    code: Code
    message: str
    value: str | None


class Kind(StrEnum):
    TEXT = "text"
    DATE = "date"
    MONEY = "money"
    DECIMAL = "decimal"
    LIST = "list"


@dataclass(frozen=True)
class FieldSpec:
    kind: Kind = Kind.TEXT
    pattern: str | None = None
    choices: type[StrEnum] | None = None
    positive: bool = False  # > 0 (money or decimal)
    min_value: Decimal | None = None
    max_value: Decimal | None = None


ID_PATTERNS = {
    "claim_id": r"CLM-\d{6}",
    "policy_number": r"POL-\d{6}",
    "provider_id": r"PRV-\d{4}",
}

FIELDS: dict[Dataset, dict[str, FieldSpec]] = {
    Dataset.POLICIES: {
        "policy_number": FieldSpec(pattern=ID_PATTERNS["policy_number"]),
        "policyholder_name": FieldSpec(),
        "insured_member_ids": FieldSpec(Kind.LIST),
        "product_name": FieldSpec(),
        "benefit_period_start": FieldSpec(Kind.DATE),
        "benefit_period_end": FieldSpec(Kind.DATE),
        "overall_limit": FieldSpec(Kind.MONEY, positive=True),
        "deductible_amount": FieldSpec(Kind.MONEY),
        "deductible_basis": FieldSpec(choices=enums.DeductibleBasis),
        "copay_percent": FieldSpec(Kind.DECIMAL, min_value=Decimal(0), max_value=Decimal(50)),
    },
    Dataset.POLICY_RULES: {
        "rule_id": FieldSpec(),
        "policy_number": FieldSpec(pattern=ID_PATTERNS["policy_number"]),
        "rule_type": FieldSpec(choices=enums.RuleType),
        "scope_type": FieldSpec(choices=enums.ScopeType),
        "scope_value": FieldSpec(),
        "limit_basis": FieldSpec(choices=enums.LimitBasis),
        "limit_amount": FieldSpec(Kind.MONEY, positive=True),
        "clause_ref": FieldSpec(),
        "description": FieldSpec(),
    },
    Dataset.CLAIMS: {
        "claim_id": FieldSpec(pattern=ID_PATTERNS["claim_id"]),
        "policy_number": FieldSpec(pattern=ID_PATTERNS["policy_number"]),
        "claimant_id": FieldSpec(),
        "claimant_name": FieldSpec(),
        "incident_date": FieldSpec(Kind.DATE),
        "submission_date": FieldSpec(Kind.DATE),
        "claim_type": FieldSpec(choices=enums.ClaimType),
        "requested_amount": FieldSpec(Kind.MONEY, positive=True),
        "incident_reference": FieldSpec(),
        "status": FieldSpec(choices=enums.ClaimStatus),
    },
    Dataset.LINE_ITEMS: {
        "line_id": FieldSpec(),
        "claim_id": FieldSpec(pattern=ID_PATTERNS["claim_id"]),
        "invoice_reference": FieldSpec(),
        "provider_id": FieldSpec(pattern=ID_PATTERNS["provider_id"]),
        "provider_name": FieldSpec(),
        "service_date": FieldSpec(Kind.DATE),
        "service_code": FieldSpec(),
        "service_description": FieldSpec(),
        "category": FieldSpec(choices=enums.Category),
        "quantity": FieldSpec(Kind.DECIMAL, positive=True),
        "unit_price": FieldSpec(Kind.MONEY),
        "line_amount": FieldSpec(Kind.MONEY),
    },
    Dataset.SETTLEMENTS: {
        "settlement_id": FieldSpec(),
        "claim_id": FieldSpec(pattern=ID_PATTERNS["claim_id"]),
        "settlement_date": FieldSpec(Kind.DATE),
        "approved_amount": FieldSpec(Kind.MONEY),
        "paid_amount": FieldSpec(Kind.MONEY),
        "settlement_status": FieldSpec(choices=enums.SettlementStatus),
    },
}

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})([-/])(\d{1,2})\2(\d{4})$")
_TWO_DIGIT_YEAR = re.compile(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{2}$")


class DateError(ValueError):
    def __init__(self, code: Code, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_date(text: str) -> date:
    """YYYY-MM-DD, DD-MM-YYYY or DD/MM/YYYY. Two-digit years are ambiguous and rejected, never guessed."""
    value = text.strip()
    if match := _ISO.match(value):
        year, month, day = int(match[1]), int(match[2]), int(match[3])
    elif match := _DMY.match(value):
        day, month, year = int(match[1]), int(match[3]), int(match[4])
    elif _TWO_DIGIT_YEAR.match(value):
        raise DateError(Code.AMBIGUOUS_DATE, f"'{value}' is ambiguous (two-digit year); use YYYY-MM-DD or DD-MM-YYYY")
    else:
        raise DateError(Code.INVALID_DATE, f"'{value}' is not a date in YYYY-MM-DD, DD-MM-YYYY or DD/MM/YYYY")
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise DateError(Code.INVALID_DATE, f"'{value}' is not a real date") from exc


def _as_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return str(raw).lower()
    if isinstance(raw, float):
        return repr(raw)
    return str(raw).strip()


def _display(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return "|".join(str(item) for item in raw)
    return _as_text(raw)


def _parse_list(raw: Any) -> list[str]:
    items = raw if isinstance(raw, list) else _as_text(raw).split("|")
    return [str(item).strip() for item in items if str(item).strip()]


def parse_field(name: str, spec: FieldSpec, raw: Any) -> tuple[Any, FieldIssue | None]:
    """Parse one non-empty raw value. Returns (value, None) or (None, issue)."""
    shown = _display(raw)

    def fail(code: Code, message: str) -> tuple[None, FieldIssue]:
        return None, FieldIssue(name, code, message, shown)

    if spec.kind is Kind.LIST:
        items = _parse_list(raw)
        return (items, None) if items else fail(Code.MISSING_FIELD, f"{name} is required")
    if spec.kind is Kind.DATE:
        try:
            return parse_date(_as_text(raw)), None
        except DateError as exc:
            return fail(exc.code, f"{name}: {exc}")
    if spec.kind is Kind.MONEY:
        try:
            amount = parse_amount(raw if isinstance(raw, int | float) and not isinstance(raw, bool) else _as_text(raw))
        except AmountError:
            return fail(Code.INVALID_AMOUNT, f"{name}: '{shown}' is not an amount like 1,42,000.50 or 142000.5")
        if amount < 0:
            return fail(Code.NEGATIVE_AMOUNT, f"{name} must not be negative ({shown})")
        if spec.positive and amount == 0:
            return fail(Code.INVALID_VALUE, f"{name} must be greater than 0")
        return amount, None
    if spec.kind is Kind.DECIMAL:
        try:
            number = Decimal(_as_text(raw).replace(",", "").rstrip("%"))
        except InvalidOperation:
            return fail(Code.INVALID_VALUE, f"{name}: '{shown}' is not a number")
        if not number.is_finite():
            return fail(Code.INVALID_VALUE, f"{name}: '{shown}' is not a number")
        if spec.positive and number <= 0:
            return fail(Code.INVALID_VALUE, f"{name} must be greater than 0")
        if spec.min_value is not None and number < spec.min_value:
            return fail(Code.INVALID_VALUE, f"{name} must be between {spec.min_value} and {spec.max_value}")
        if spec.max_value is not None and number > spec.max_value:
            return fail(Code.INVALID_VALUE, f"{name} must be between {spec.min_value} and {spec.max_value}")
        return number, None
    text = _as_text(raw)
    if spec.pattern and not re.fullmatch(spec.pattern, text):
        return fail(Code.INVALID_FORMAT, f"{name} '{text}' does not match {spec.pattern.replace(chr(92) + 'd', '9')}")
    if spec.choices is not None:
        value = text.lower()
        allowed = [choice.value for choice in spec.choices]
        if value not in allowed:
            return fail(Code.INVALID_VALUE, f"{name} '{text}' must be one of {', '.join(allowed)}")
        return value, None
    return text, None


@dataclass
class ParsedRow:
    values: dict[str, Any] = field(default_factory=dict)
    issues: list[FieldIssue] = field(default_factory=list)


def is_blank(raw: Any) -> bool:
    if raw is None:
        return True
    if isinstance(raw, list):
        return not raw
    return _as_text(raw) == ""


def parse_row(dataset: Dataset, required: tuple[str, ...], fields: dict[str, Any]) -> ParsedRow:
    """Parse a row's mapped fields (field name -> raw value) against its dataset contract."""
    parsed = ParsedRow()
    for name, spec in FIELDS[dataset].items():
        raw = fields.get(name)
        if is_blank(raw):
            parsed.values[name] = None
            if name in required:
                parsed.issues.append(FieldIssue(name, Code.MISSING_FIELD, f"{name} is required", None))
            continue
        value, issue = parse_field(name, spec, raw)
        parsed.values[name] = value
        if issue:
            parsed.issues.append(issue)
    return parsed
