"""Turn raw tables into validated rows: field checks, then cross-record checks in load order.

Every row ends as accepted, accepted with warnings, or rejected with reasons; nothing is dropped silently.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.core import enums
from app.core.enums import IssueSeverity
from app.core.money import q2
from app.ingest.mapping import LOAD_ORDER, SPECS, Dataset, map_headers
from app.ingest.readers import RawTable
from app.ingest.schemas import Code, parse_row

AMOUNT_TOLERANCE = Decimal("1.00")
SERVICE_DATE_WINDOW = timedelta(days=30)
UNRECOGNISED = "unrecognised"


class RowStatus(StrEnum):
    ACCEPTED = "accepted"
    WARNINGS = "warnings"
    REJECTED = "rejected"


@dataclass
class Issue:
    severity: IssueSeverity
    code: Code
    message: str
    field: str | None = None
    value: str | None = None


@dataclass
class Row:
    dataset: Dataset
    file_name: str
    sheet: str | None
    row_number: int
    raw: dict[str, Any]
    values: dict[str, Any]
    extra: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)
    dataset_rejected: bool = False

    @property
    def status(self) -> RowStatus:
        if self.dataset_rejected or any(i.severity is IssueSeverity.ERROR for i in self.issues):
            return RowStatus.REJECTED
        return RowStatus.WARNINGS if self.issues else RowStatus.ACCEPTED

    @property
    def ok(self) -> bool:
        return self.status is not RowStatus.REJECTED

    def error(self, code: Code, message: str, field_name: str | None = None) -> None:
        value = self.values.get(field_name) if field_name else None
        self.issues.append(Issue(IssueSeverity.ERROR, code, message, field_name, _show(value)))

    def warn(self, code: Code, message: str, field_name: str | None = None) -> None:
        value = self.values.get(field_name) if field_name else None
        self.issues.append(Issue(IssueSeverity.WARNING, code, message, field_name, _show(value)))

    @property
    def source_row(self) -> dict[str, Any]:
        source: dict[str, Any] = {"file_name": self.file_name, "sheet": self.sheet, "row_number": self.row_number}
        if self.extra:
            source["extra"] = {k: _show(v) for k, v in self.extra.items()}
        return source


@dataclass
class TableIssue:
    """A problem with a whole file, sheet or dataset (no single row)."""

    file_name: str
    sheet: str | None
    dataset: str | None
    severity: IssueSeverity
    code: Code
    message: str
    field: str | None = None


@dataclass
class ExistingData:
    """What the database already holds, for references and "ID already exists" checks."""

    policies: dict[str, list[str]] = field(default_factory=dict)  # policy_number -> insured member ids
    rule_ids: set[str] = field(default_factory=set)
    claims: dict[str, tuple[str, date, date]] = field(default_factory=dict)  # id -> (status, incident, submission)
    line_ids: set[str] = field(default_factory=set)
    settlement_ids: set[str] = field(default_factory=set)
    service_codes: set[str] = field(default_factory=set)


@dataclass
class ValidationResult:
    rows: dict[Dataset, list[Row]]
    table_issues: list[TableIssue]
    unrecognised_rows: int = 0

    def accepted(self, dataset: Dataset) -> list[Row]:
        return [row for row in self.rows.get(dataset, []) if row.ok]

    def counts(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}
        for dataset in LOAD_ORDER:
            rows = self.rows.get(dataset, [])
            if not rows:
                continue
            tally = {status.value: sum(1 for r in rows if r.status is status) for status in RowStatus}
            counts[dataset.value] = {"received": len(rows), **tally}
        if self.unrecognised_rows:
            counts[UNRECOGNISED] = {"received": self.unrecognised_rows, "accepted": 0, "warnings": 0, "rejected": 0}
            counts[UNRECOGNISED]["rejected"] = self.unrecognised_rows
        return counts


def reconciles(counts: dict[str, dict[str, int]]) -> bool:
    return all(c["received"] == c["accepted"] + c["warnings"] + c["rejected"] for c in counts.values())


def _show(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "|".join(str(v) for v in value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _build_rows(tables: list[RawTable], result: ValidationResult) -> None:
    for table in tables:
        if table.dataset is None:
            result.unrecognised_rows += len(table.rows)
            where = f"sheet '{table.sheet}'" if table.sheet else "file"
            result.table_issues.append(
                TableIssue(
                    table.file_name,
                    table.sheet,
                    None,
                    IssueSeverity.ERROR,
                    Code.UNKNOWN_DATASET,
                    f"Could not tell which dataset this {where} holds from its name or headers; "
                    f"{len(table.rows)} rows were not imported",
                )
            )
            continue
        spec = SPECS[table.dataset]
        header_map = map_headers(table.dataset, table.headers)
        for header in header_map.unknown:
            result.table_issues.append(
                TableIssue(
                    table.file_name,
                    table.sheet,
                    table.dataset.value,
                    IssueSeverity.WARNING,
                    Code.UNKNOWN_COLUMN,
                    f"Column '{header}' is not part of {table.dataset.value}; its values are kept as extra data",
                    header,
                )
            )
        if header_map.missing:
            result.table_issues.append(
                TableIssue(
                    table.file_name,
                    table.sheet,
                    table.dataset.value,
                    IssueSeverity.ERROR,
                    Code.MISSING_COLUMN,
                    f"{table.dataset.value} is missing required column(s): {', '.join(header_map.missing)}; "
                    f"none of its {len(table.rows)} rows were imported",
                )
            )
        rows = result.rows.setdefault(table.dataset, [])
        for raw_row in table.rows:
            mapped = {target: raw_row.values.get(header) for header, target in header_map.columns.items()}
            extra = {h: raw_row.values.get(h) for h in header_map.unknown}
            row = Row(table.dataset, table.file_name, table.sheet, raw_row.row_number, raw_row.values, {}, extra)
            if header_map.missing:
                row.dataset_rejected = True
            else:
                parsed = parse_row(table.dataset, spec.required, mapped)
                row.values = parsed.values
                for issue in parsed.issues:
                    row.issues.append(Issue(IssueSeverity.ERROR, issue.code, issue.message, issue.field, issue.value))
            rows.append(row)


def _check_unique(rows: list[Row], key: str, existing: set[str] | dict) -> dict[str, Row]:
    """First occurrence of an ID wins; later ones in the file, or IDs already stored, are rejected."""
    seen: dict[str, Row] = {}
    for row in rows:
        value = row.values.get(key)
        if value is None or row.dataset_rejected:
            continue
        if value in seen:
            first = seen[value]
            row.error(
                Code.DUPLICATE_ID_IN_FILE,
                f"{key} {value} appears more than once (first at row {first.row_number})",
                key,
            )
        elif value in existing:
            row.error(Code.ID_EXISTS, f"{key} {value} already exists", key)
        else:
            seen[value] = row
    return seen


def _validate_policies(rows: list[Row], existing: ExistingData) -> dict[str, Row]:
    for row in rows:
        start, end = row.values.get("benefit_period_start"), row.values.get("benefit_period_end")
        if start and end and end <= start:
            row.error(
                Code.PERIOD_END_BEFORE_START,
                "benefit_period_end must be after benefit_period_start",
                "benefit_period_end",
            )
    return _check_unique(rows, "policy_number", existing.policies)


def _validate_rules(rows: list[Row], policies_in_file: dict[str, Row], existing: ExistingData) -> None:
    valid_scope = {
        enums.ScopeType.CATEGORY.value: {c.value for c in enums.Category},
        enums.ScopeType.CLAIM_TYPE.value: {c.value for c in enums.ClaimType},
        enums.ScopeType.SERVICE_CODE.value: existing.service_codes,
    }
    for row in rows:
        values = row.values
        if values.get("rule_type") == enums.RuleType.SUB_LIMIT.value:
            for name in ("limit_basis", "limit_amount"):
                if values.get(name) is None and not any(i.field == name for i in row.issues):
                    row.error(Code.MISSING_FIELD, f"{name} is required for sub-limit rules", name)
        scope_type, scope_value = values.get("scope_type"), values.get("scope_value")
        if scope_type in valid_scope and scope_value is not None:
            normalised = scope_value if scope_type == enums.ScopeType.SERVICE_CODE.value else scope_value.lower()
            if normalised not in valid_scope[scope_type]:
                row.error(Code.INVALID_VALUE, f"scope_value '{scope_value}' is not a valid {scope_type}", "scope_value")
            else:
                values["scope_value"] = normalised
        _check_policy_reference(row, policies_in_file, existing)
    _check_unique(rows, "rule_id", existing.rule_ids)


def _check_policy_reference(row: Row, policies_in_file: dict[str, Row], existing: ExistingData) -> None:
    policy = row.values.get("policy_number")
    if policy is None:
        return
    if policy in policies_in_file:
        if not policies_in_file[policy].ok:
            row.error(Code.PARENT_REJECTED, f"parent policy rejected: {policy}", "policy_number")
    elif policy not in existing.policies:
        row.error(Code.UNKNOWN_POLICY, f"policy_number {policy} does not exist", "policy_number")


def _policy_members(policy: str, policies_in_file: dict[str, Row], existing: ExistingData) -> list[str] | None:
    if policy in policies_in_file:
        return policies_in_file[policy].values.get("insured_member_ids") or []
    return existing.policies.get(policy)


def _validate_claims(
    rows: list[Row], policies_in_file: dict[str, Row], existing: ExistingData, today: date
) -> dict[str, Row]:
    for row in rows:
        values = row.values
        incident, submission = values.get("incident_date"), values.get("submission_date")
        if incident and incident > today:
            row.error(Code.FUTURE_DATE, f"incident_date {incident.isoformat()} is in the future", "incident_date")
        if incident and submission and submission < incident:
            row.error(
                Code.SUBMISSION_BEFORE_INCIDENT,
                f"submission_date {submission.isoformat()} is before incident_date {incident.isoformat()}",
                "submission_date",
            )
        _check_policy_reference(row, policies_in_file, existing)
        policy, claimant = values.get("policy_number"), values.get("claimant_id")
        if row.ok and policy and claimant:
            members = _policy_members(policy, policies_in_file, existing)
            if members is not None and claimant not in members:
                row.warn(
                    Code.CLAIMANT_NOT_INSURED,
                    f"claimant {claimant} is not an insured member of {policy}; the claim will fail coverage",
                    "claimant_id",
                )
    return _check_unique(rows, "claim_id", existing.claims)


def _claim_reference(row: Row, claims_in_file: dict[str, Row], existing: ExistingData) -> tuple[str, date, date] | None:
    """(status, incident_date, submission_date) of the referenced claim, or None after recording the error."""
    claim_id = row.values.get("claim_id")
    if claim_id is None:
        return None
    if claim_id in claims_in_file:
        parent = claims_in_file[claim_id]
        if not parent.ok:
            row.error(Code.PARENT_REJECTED, f"parent claim rejected: {claim_id}", "claim_id")
            return None
        v = parent.values
        return v["status"], v["incident_date"], v["submission_date"]
    if claim_id in existing.claims:
        return existing.claims[claim_id]
    row.error(Code.UNKNOWN_CLAIM, f"claim_id {claim_id} does not exist", "claim_id")
    return None


def _validate_lines(rows: list[Row], claims_in_file: dict[str, Row], existing: ExistingData) -> None:
    for row in rows:
        values = row.values
        code = values.get("service_code")
        if code is not None and code not in existing.service_codes:
            row.error(Code.UNKNOWN_SERVICE_CODE, f"service_code {code} is not in the reference list", "service_code")
        quantity, unit_price, amount = values.get("quantity"), values.get("unit_price"), values.get("line_amount")
        if None not in (quantity, unit_price, amount):
            expected = q2(quantity * unit_price)
            if abs(expected - amount) > AMOUNT_TOLERANCE:
                row.error(
                    Code.LINE_AMOUNT_MISMATCH,
                    f"line_amount {amount} does not equal quantity × unit_price = {expected}",
                    "line_amount",
                )
        parent = _claim_reference(row, claims_in_file, existing)
        service_date = values.get("service_date")
        if parent and service_date and abs(service_date - parent[1]) > SERVICE_DATE_WINDOW:
            row.warn(
                Code.SERVICE_DATE_FAR,
                f"service_date {service_date.isoformat()} is more than 30 days from the incident date",
                "service_date",
            )
    _check_unique(rows, "line_id", existing.line_ids)


def _validate_settlements(rows: list[Row], claims_in_file: dict[str, Row], existing: ExistingData) -> None:
    for row in rows:
        values = row.values
        parent = _claim_reference(row, claims_in_file, existing)
        if parent:
            status, _, submitted = parent
            if status != enums.ClaimStatus.SETTLED.value:
                row.error(Code.CLAIM_NOT_SETTLED, f"claim {values['claim_id']} is not settled", "claim_id")
            settled_on = values.get("settlement_date")
            if settled_on and settled_on < submitted:
                row.error(
                    Code.SETTLEMENT_BEFORE_SUBMISSION,
                    f"settlement_date {settled_on.isoformat()} is before the claim's submission date",
                    "settlement_date",
                )
        approved, paid = values.get("approved_amount"), values.get("paid_amount")
        if approved is not None and paid is not None and paid > approved:
            row.warn(Code.PAID_ABOVE_APPROVED, f"paid_amount {paid} is above approved_amount {approved}", "paid_amount")
    _check_unique(rows, "settlement_id", existing.settlement_ids)


def _check_requested_amounts(claims: dict[str, Row], lines: list[Row]) -> None:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    has_lines: set[str] = set()
    for line in lines:
        claim_id = line.values.get("claim_id")
        if line.ok and claim_id in claims:
            totals[claim_id] += line.values["line_amount"]
            has_lines.add(claim_id)
    for claim_id in has_lines:
        claim = claims[claim_id]
        requested = claim.values.get("requested_amount")
        if claim.ok and requested is not None and abs(requested - totals[claim_id]) > AMOUNT_TOLERANCE:
            claim.warn(
                Code.REQUESTED_AMOUNT_MISMATCH,
                f"requested_amount {requested} differs from the sum of its line items {totals[claim_id]}",
                "requested_amount",
            )


def validate_tables(tables: list[RawTable], existing: ExistingData, today: date) -> ValidationResult:
    result = ValidationResult(rows={}, table_issues=[])
    _build_rows(tables, result)
    rows = {dataset: result.rows.get(dataset, []) for dataset in LOAD_ORDER}
    policies = _validate_policies(rows[Dataset.POLICIES], existing)
    _validate_rules(rows[Dataset.POLICY_RULES], policies, existing)
    claims = _validate_claims(rows[Dataset.CLAIMS], policies, existing, today)
    _validate_lines(rows[Dataset.LINE_ITEMS], claims, existing)
    _validate_settlements(rows[Dataset.SETTLEMENTS], claims, existing)
    _check_requested_amounts(claims, rows[Dataset.LINE_ITEMS])
    return result
