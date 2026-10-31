"""Independent checker: validates raw rows, recomputes every policy and duplicate finding, compares with the key.

It knows nothing about how the builder planted scenarios. It reads the rows as the importer would, applies the
plan's rules (Phases 2-4) and reports what it finds, so the answer key is verified rather than asserted.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Any

from app.core.money import AmountError, parse_amount
from scripts.datagen.common import (
    CATEGORIES,
    CLAIM_TYPES,
    DATASETS,
    ID_FIELDS,
    NEAR_DUPLICATE_THRESHOLD,
    TODAY,
    ZERO,
    near_score,
    norm_ref,
    parse_date,
    percent_of,
    ref_similarity,
    service_codes,
)

Row = dict[str, Any]

REQUIRED = {
    "policies": [
        "policy_number", "policyholder_name", "insured_member_ids", "product_name", "benefit_period_start",
        "benefit_period_end", "overall_limit", "deductible_amount", "deductible_basis", "copay_percent",
    ],
    "policy_rules": ["rule_id", "policy_number", "rule_type", "scope_type", "scope_value", "clause_ref"],
    "claims": [
        "claim_id", "policy_number", "claimant_id", "claimant_name", "incident_date", "submission_date", "claim_type",
        "requested_amount", "status",
    ],
    "line_items": [
        "line_id", "claim_id", "invoice_reference", "provider_id", "provider_name", "service_date", "service_code",
        "service_description", "category", "quantity", "unit_price", "line_amount",
    ],
    "settlements": [
        "settlement_id", "claim_id", "settlement_date", "approved_amount", "paid_amount", "settlement_status",
    ],
}  # fmt: skip
PATTERNS = {
    "policy_number": re.compile(r"POL-\d{6}"),
    "claim_id": re.compile(r"CLM-\d{6}"),
    "provider_id": re.compile(r"PRV-\d{4}"),
}
CHECK_CATEGORY = {
    "C01": "OUT_OF_BENEFIT_PERIOD",
    "C02": "NOT_COVERED",
    "C03": "NOT_COVERED",
    "C04": "NOT_COVERED",
    "C05": "EXCLUDED_SERVICE",
    "C06": "SUB_LIMIT_EXCEEDED",
    "C07": "SUB_LIMIT_EXCEEDED",
    "C08": "SUB_LIMIT_EXCEEDED",
    "C11": "OVERALL_LIMIT_EXCEEDED",
    "C12": "SETTLEMENT_OVERPAYMENT",
}


@dataclass
class PolicyRec:
    number: str
    members: set[str]
    start: date
    end: date
    limit: Decimal
    deductible: Decimal
    basis: str
    copay: Decimal
    rules: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ClaimRec:
    claim_id: str
    policy: str
    claimant: str
    incident: date
    submission: date
    claim_type: str
    requested: Decimal
    incident_ref: str
    status: str
    lines: list["LineRec"] = field(default_factory=list)
    settlement: "SettlementRec | None" = None


@dataclass
class LineRec:
    line_id: str
    claim_id: str
    ref: str
    provider: str
    day: date
    code: str
    category: str
    qty: Decimal
    price: Decimal
    amount: Decimal


@dataclass
class SettlementRec:
    settlement_id: str
    claim_id: str
    day: date
    approved: Decimal
    paid: Decimal


@dataclass
class Report:
    issues: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    legit: list[dict[str, Any]] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    near_scores: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    accepted: dict[str, int] = field(default_factory=dict)
    claims: dict[str, ClaimRec] = field(default_factory=dict)


# ---- Phase 2: row validation --------------------------------------------------------------------------------


class RowCheck:
    def __init__(self, report: Report, dataset: str, index: int, row: Row) -> None:
        self.report, self.dataset, self.index, self.row = report, dataset, index, row
        self.problems: list[tuple[str, str | None]] = []

    def text(self, name: str) -> str | None:
        value = self.row.get(name)
        if isinstance(value, str):
            value = value.strip()
        return value or None

    def problem(self, code: str, name: str | None) -> None:
        self.problems.append((code, name))

    def date(self, name: str) -> date | None:
        value = self.text(name)
        if value is None:
            return None
        parsed, error = parse_date(value)
        if error:
            self.problem(error, name)
        return parsed

    def amount(self, name: str, allow_zero: bool = True) -> Decimal | None:
        value = self.text(name)
        if value is None:
            return None
        try:
            parsed = parse_amount(value)
        except AmountError:
            self.problem("invalid_amount", name)
            return None
        if parsed < 0:
            self.problem("negative_amount", name)
        elif parsed == 0 and not allow_zero:
            self.problem("invalid_value", name)
        return parsed

    def enum(self, name: str, allowed: tuple[str, ...] | set[str]) -> str | None:
        value = self.text(name)
        if value is not None and value not in allowed:
            self.problem("invalid_value", name)
        return value

    def finish(self, severity: str = "error") -> bool:
        record = self.text(ID_FIELDS[self.dataset])
        for code, name in self.problems:
            self.report.issues.append(
                {
                    "dataset": self.dataset,
                    "row_index": self.index,
                    "record_id": record,
                    "error_code": code,
                    "severity": severity,
                    "field": name,
                }
            )
        return not self.problems


def _start(report: Report, dataset: str, index: int, row: Row, seen: set[str]) -> RowCheck:
    check = RowCheck(report, dataset, index, row)
    for name in REQUIRED[dataset]:
        if check.text(name) is None:
            check.problem("missing_field", name)
    key = check.text(ID_FIELDS[dataset])
    if key is not None:
        pattern = PATTERNS.get(ID_FIELDS[dataset])
        if pattern and not pattern.fullmatch(key):
            check.problem("invalid_format", ID_FIELDS[dataset])
        if key in seen:
            check.problem("duplicate_id_in_file", ID_FIELDS[dataset])
        seen.add(key)
    return check


def _parent(check: RowCheck, name: str, accepted: set[str], in_file: set[str], unknown: str) -> bool:
    value = check.text(name)
    if value is None or value in accepted:
        return True
    if value in in_file:
        check.problems = [("parent_rejected", name)]
        return False
    check.problem(unknown, name)
    return False


def validate(rows: dict[str, list[Row]], report: Report) -> tuple[dict[str, PolicyRec], dict[str, ClaimRec]]:
    codes = service_codes()
    policies: dict[str, PolicyRec] = {}
    seen: set[str] = set()
    for i, row in enumerate(rows["policies"]):
        c = _start(report, "policies", i, row, seen)
        start, end = c.date("benefit_period_start"), c.date("benefit_period_end")
        limit = c.amount("overall_limit", allow_zero=False)
        deductible = c.amount("deductible_amount")
        basis = c.enum("deductible_basis", ("per_claim", "per_period"))
        copay = c.amount("copay_percent")
        if copay is not None and not 0 <= copay <= 50:
            c.problem("invalid_value", "copay_percent")
        if start and end and end <= start:
            c.problem("invalid_value", "benefit_period_end")
        members = row.get("insured_member_ids") or []
        if c.finish():
            policies[row["policy_number"]] = PolicyRec(
                row["policy_number"],
                set(members),
                start,
                end,
                limit,
                deductible,
                basis,
                copay,  # type: ignore[arg-type]
            )
    policy_ids_in_file = {r.get("policy_number") for r in rows["policies"]}

    seen = set()
    for i, row in enumerate(rows["policy_rules"]):
        c = _start(report, "policy_rules", i, row, seen)
        rule_type = c.enum("rule_type", ("coverage", "exclusion", "sub_limit"))
        scope_type = c.enum("scope_type", ("category", "service_code", "claim_type"))
        scope_value = c.text("scope_value")
        allowed = {"category": set(CATEGORIES), "service_code": set(codes), "claim_type": set(CLAIM_TYPES)}
        if scope_type in allowed and scope_value is not None and scope_value not in allowed[scope_type]:
            c.problem("invalid_value", "scope_value")
        basis, amount = None, None
        if rule_type == "sub_limit":
            basis = c.enum("limit_basis", ("per_day", "per_claim", "per_period"))
            if basis is None:
                c.problem("missing_field", "limit_basis")
            if c.text("limit_amount") is None:
                c.problem("missing_field", "limit_amount")
            amount = c.amount("limit_amount", allow_zero=False)
        _parent(c, "policy_number", set(policies), policy_ids_in_file, "unknown_policy")  # type: ignore[arg-type]
        if c.finish():
            policies[row["policy_number"]].rules.append(
                {
                    "rule_id": row["rule_id"],
                    "rule_type": rule_type,
                    "scope_type": scope_type,
                    "scope_value": scope_value,
                    "basis": basis,
                    "amount": amount,
                }
            )

    claims: dict[str, ClaimRec] = {}
    seen = set()
    for i, row in enumerate(rows["claims"]):
        c = _start(report, "claims", i, row, seen)
        incident, submission = c.date("incident_date"), c.date("submission_date")
        if incident and incident > TODAY:
            c.problem("invalid_value", "incident_date")
        if incident and submission and submission < incident:
            c.problem("submission_before_incident", "submission_date")
        claim_type = c.enum("claim_type", CLAIM_TYPES)
        requested = c.amount("requested_amount", allow_zero=False)
        status = c.enum("status", ("open", "settled"))
        _parent(c, "policy_number", set(policies), policy_ids_in_file, "unknown_policy")  # type: ignore[arg-type]
        if c.finish():
            claims[row["claim_id"]] = ClaimRec(
                row["claim_id"], row["policy_number"], row["claimant_id"], incident, submission,  # type: ignore[arg-type]
                claim_type, requested, norm_ref(row.get("incident_reference")), status,  # type: ignore[arg-type]
            )  # fmt: skip
    claim_ids_in_file = {r.get("claim_id") for r in rows["claims"]}

    seen = set()
    for i, row in enumerate(rows["line_items"]):
        c = _start(report, "line_items", i, row, seen)
        day = c.date("service_date")
        code = c.text("service_code")
        if code is not None and code not in codes:
            c.problem("unknown_service_code", "service_code")
        category = c.enum("category", CATEGORIES)
        provider = c.text("provider_id")
        if provider and not PATTERNS["provider_id"].fullmatch(provider):
            c.problem("invalid_format", "provider_id")
        qty = c.amount("quantity", allow_zero=False)
        price = c.amount("unit_price")
        amount = c.amount("line_amount")
        if qty is not None and price is not None and amount is not None and amount >= 0 and price >= 0:
            if abs(qty * price - amount) > 1:
                c.problem("line_amount_mismatch", "line_amount")
        _parent(c, "claim_id", set(claims), claim_ids_in_file, "unknown_claim")  # type: ignore[arg-type]
        parent = claims.get(row.get("claim_id"))  # type: ignore[arg-type]
        if parent is not None and day is not None and abs((day - parent.incident).days) > 30:
            report.anomalies.append(f"line {row.get('line_id')} is more than 30 days from its incident date")
        if c.finish():
            claims[row["claim_id"]].lines.append(
                LineRec(row["line_id"], row["claim_id"], norm_ref(row["invoice_reference"]), provider, day, code,  # type: ignore[arg-type]
                        category, qty, price, amount)  # type: ignore[arg-type]
            )  # fmt: skip

    for i, row in enumerate(rows["claims"]):
        claim = claims.get(row.get("claim_id"))  # type: ignore[arg-type]
        if claim is None or report.claims.get(claim.claim_id) is not None:
            continue
        report.claims[claim.claim_id] = claim
        if abs(sum((line.amount for line in claim.lines), ZERO) - claim.requested) > 1:
            c = RowCheck(report, "claims", i, row)
            c.problem("requested_amount_mismatch", "requested_amount")
            c.finish("warning")

    seen = set()
    for i, row in enumerate(rows["settlements"]):
        c = _start(report, "settlements", i, row, seen)
        day = c.date("settlement_date")
        approved, paid = c.amount("approved_amount"), c.amount("paid_amount")
        c.enum("settlement_status", ("paid", "partially_paid", "rejected"))
        if _parent(c, "claim_id", set(claims), claim_ids_in_file, "unknown_claim"):
            parent = claims.get(row.get("claim_id"))  # type: ignore[arg-type]
            if parent is not None and parent.status != "settled":
                c.problem("invalid_value", "claim_id")
            if parent is not None and day is not None and day < parent.submission:
                c.problem("invalid_value", "settlement_date")
        if c.finish():
            parent = claims[row["claim_id"]]
            if parent.settlement is not None:
                report.anomalies.append(f"{parent.claim_id} has more than one accepted settlement")
            parent.settlement = SettlementRec(row["settlement_id"], row["claim_id"], day, approved, paid)  # type: ignore[arg-type]

    rejected: dict[str, set[int]] = defaultdict(set)
    for issue in report.issues:
        if issue["severity"] == "error":
            rejected[issue["dataset"]].add(issue["row_index"])
    report.accepted = {ds: len(rows[ds]) - len(rejected[ds]) for ds in DATASETS}
    return policies, claims


# ---- Phase 3: policy rules and payable -----------------------------------------------------------------------


def _matches(rule: dict[str, Any], line: LineRec) -> bool:
    if rule["scope_type"] == "category":
        return rule["scope_value"] == line.category
    if rule["scope_type"] == "service_code":
        return rule["scope_value"] == line.code
    return False


def evaluate_policies(policies: dict[str, PolicyRec], claims: dict[str, ClaimRec], report: Report) -> None:
    by_policy: dict[str, list[ClaimRec]] = defaultdict(list)
    for claim in claims.values():
        by_policy[claim.policy].append(claim)
        if claim.status == "settled" and claim.settlement is None:
            report.anomalies.append(f"settled claim {claim.claim_id} has no settlement")

    def emit(claim: ClaimRec, check: str, amount: Decimal, line: str | None = None, rule: str | None = None) -> None:
        if claim.status == "settled" and check != "C12":
            report.anomalies.append(f"settled claim {claim.claim_id} fails {check}")
            return
        report.findings.append(
            {
                "category": CHECK_CATEGORY[check],
                "check_code": check,
                "match_type": None,
                "claim_id": claim.claim_id,
                "line_id": line,
                "policy_rule_id": rule,
                "matched_claim_id": None,
                "expected_amount": f"{amount:.2f}",
            }
        )

    for number, policy_claims in by_policy.items():
        policy = policies[number]
        rules = sorted(policy.rules, key=lambda r: r["rule_id"])
        coverage = [r for r in rules if r["rule_type"] == "coverage"]
        exclusions = [r for r in rules if r["rule_type"] == "exclusion"]
        limits = [r for r in rules if r["rule_type"] == "sub_limit"]
        covered_types = {r["scope_value"] for r in coverage if r["scope_type"] == "claim_type"}
        deductible_used = ZERO
        period_used: dict[str, Decimal] = defaultdict(lambda: ZERO)
        overall_used = ZERO
        for claim in sorted(policy_claims, key=lambda c: (c.incident, c.submission, c.claim_id)):
            failures = []
            if not policy.start <= claim.incident <= policy.end:
                failures.append("C01")
            if claim.claimant not in policy.members:
                failures.append("C02")
            if claim.claim_type not in covered_types:
                failures.append("C03")
            if failures:
                for check in failures:
                    emit(claim, check, claim.requested)
                continue
            kept = []
            for line in claim.lines:
                excluded = next((r for r in exclusions if _matches(r, line)), None)
                if not any(_matches(r, line) for r in coverage):
                    emit(claim, "C04", line.amount, line.line_id)
                elif excluded:
                    emit(claim, "C05", line.amount, line.line_id, excluded["rule_id"])
                else:
                    kept.append(line)
            amount = sum((line.amount for line in kept), ZERO)
            for rule in limits:
                scope = [line for line in kept if _matches(rule, line)]
                if not scope:
                    continue
                limit = rule["amount"]
                total = sum((line.amount for line in scope), ZERO)
                if rule["basis"] == "per_day":
                    for line in scope:
                        if line.qty > 1 and line.price > limit:
                            excess = (line.price - limit) * line.qty
                            emit(claim, "C06", excess, line.line_id, rule["rule_id"])
                            amount -= excess
                    days: dict[date, list[LineRec]] = defaultdict(list)
                    for line in scope:
                        if line.qty <= 1:
                            days[line.day].append(line)
                    for day_lines in days.values():
                        day_total = sum((line.amount for line in day_lines), ZERO)
                        if day_total > limit:
                            only = day_lines[0].line_id if len(day_lines) == 1 else None
                            emit(claim, "C06", day_total - limit, only, rule["rule_id"])
                            amount -= day_total - limit
                elif rule["basis"] == "per_claim":
                    if total > limit:
                        emit(claim, "C07", total - limit, None, rule["rule_id"])
                        amount -= total - limit
                else:
                    remaining = max(limit - period_used[rule["rule_id"]], ZERO)
                    if total > remaining:
                        emit(claim, "C08", total - remaining, None, rule["rule_id"])
                        amount -= total - remaining
                    period_used[rule["rule_id"]] += min(total, remaining)
            available = policy.deductible if policy.basis == "per_claim" else policy.deductible - deductible_used
            applied = min(available, amount)
            if policy.basis == "per_period":
                deductible_used += applied
            amount -= applied
            amount -= percent_of(amount, policy.copay)
            remaining_overall = policy.limit - overall_used
            if amount > remaining_overall:
                emit(claim, "C11", amount - remaining_overall)
                amount = remaining_overall
            if claim.status == "open":
                overall_used += amount
            elif claim.settlement is not None:
                overall_used += claim.settlement.paid
                if claim.settlement.paid > amount:
                    emit(claim, "C12", claim.settlement.paid - amount)
                elif claim.settlement.paid > claim.settlement.approved:
                    report.anomalies.append(f"{claim.claim_id} paid above approved but within entitlement")


# ---- Phase 4: duplicates ------------------------------------------------------------------------------------


def _dup(kind: str, category: str, claim: ClaimRec, amount: Decimal, **extra: Any) -> dict[str, Any]:
    finding = {
        "category": category,
        "check_code": None,
        "match_type": kind,
        "claim_id": claim.claim_id,
        "line_id": None,
        "policy_rule_id": None,
        "matched_claim_id": None,
        "expected_amount": f"{amount:.2f}",
    }
    finding.update(extra)
    return finding


def _window_max(days: list[date]) -> int:
    days = sorted(days)
    return max(sum(1 for d in days if start <= d <= start + timedelta(days=6)) for start in days)


def evaluate_duplicates(claims: dict[str, ClaimRec], report: Report) -> None:
    codes = service_codes()
    order = {c.claim_id: (c.submission, c.claim_id) for c in claims.values()}
    by_claimant: dict[str, list[ClaimRec]] = defaultdict(list)
    for claim in claims.values():
        by_claimant[claim.claimant].append(claim)

    exact_pairs: set[tuple[str, str]] = set()
    for group in by_claimant.values():
        for a, b in combinations(sorted(group, key=lambda c: order[c.claim_id]), 2):
            same_invoices = {x.provider for x in a.lines} == {x.provider for x in b.lines} and {
                x.ref for x in a.lines
            } == {x.ref for x in b.lines}
            same_incident = bool(a.incident_ref) and (a.incident_ref, a.incident, a.requested) == (
                b.incident_ref,
                b.incident,
                b.requested,
            )
            if same_invoices or same_incident:
                exact_pairs.add((a.claim_id, b.claim_id))
                report.findings.append(
                    _dup("exact_claim", "EXACT_DUPLICATE_CLAIM", b, b.requested, matched_claim_id=a.claim_id)
                )

    for claim in claims.values():
        groups: dict[tuple[Any, ...], list[LineRec]] = defaultdict(list)
        for line in claim.lines:
            groups[(line.code, line.day, line.qty, line.price)].append(line)
        for lines in groups.values():
            for line in sorted(lines, key=lambda x: x.line_id)[1:]:
                report.findings.append(
                    _dup("duplicate_line", "DUPLICATE_LINE_ITEM", claim, line.amount, line_id=line.line_id)
                )

    index: dict[tuple[Any, ...], list[LineRec]] = defaultdict(list)
    for claim in claims.values():
        for line in claim.lines:
            index[(line.ref, line.code, line.day, line.amount)].append(line)
    for lines in index.values():
        owners = sorted({line.claim_id for line in lines}, key=lambda cid: order[cid])
        if len(owners) < 2:
            continue
        original = owners[0]
        for line in lines:
            if line.claim_id == original or (original, line.claim_id) in exact_pairs:
                continue
            report.findings.append(
                _dup(
                    "duplicate_line",
                    "DUPLICATE_LINE_ITEM",
                    claims[line.claim_id],
                    line.amount,
                    line_id=line.line_id,
                    matched_claim_id=original,
                )
            )

    for group in by_claimant.values():
        code_days: dict[str, list[date]] = defaultdict(list)
        for claim in group:
            for line in claim.lines:
                code_days[line.code].append(line.day)
        for a, b in combinations(sorted(group, key=lambda c: order[c.claim_id]), 2):
            if (a.claim_id, b.claim_id) in exact_pairs:
                continue
            if not {x.provider for x in a.lines} & {x.provider for x in b.lines}:
                continue
            incident_gap = abs((a.incident - b.incident).days)
            service_gap = min(abs((x.day - y.day).days) for x in a.lines for y in b.lines)
            if min(incident_gap, service_gap) > 7:
                continue
            refs_a, refs_b = {x.ref for x in a.lines}, {x.ref for x in b.lines}
            sims = [ref_similarity(x, y) for x in refs_a for y in refs_b]
            sim_hi = max(sims)
            sim_lo = min(max(ref_similarity(y, x) for x in refs_a) for y in refs_b)
            diff = abs(a.requested - b.requested)
            diffs = [float(diff / max(a.requested, b.requested)), float(diff / min(a.requested, b.requested))]
            diffs.append(float(diff / a.requested))
            codes_a, codes_b = {x.code for x in a.lines}, {x.code for x in b.lines}
            jaccard = len(codes_a & codes_b) / len(codes_a | codes_b)
            score_hi = near_score(sim_hi, min(incident_gap, service_gap), min(diffs), jaccard)
            score_lo = near_score(sim_lo, max(incident_gap, service_gap), max(diffs), jaccard)
            overlap = codes_a & codes_b
            if overlap and all(codes[c].repeatable for c in overlap):
                ok = sim_hi < 0.90
                for code in overlap:
                    gap = min(abs((x.day - y.day).days) for x in a.lines for y in b.lines if x.code == y.code == code)
                    ok = ok and gap >= (codes[code].min_interval_days or 0)
                    ok = ok and _window_max(code_days[code]) <= (codes[code].max_per_week or 0)
                if ok:
                    for code in sorted(overlap):
                        report.legit.append(
                            {
                                "claim_id": b.claim_id,
                                "line_id": next(x.line_id for x in b.lines if x.code == code),
                                "matched_claim_id": a.claim_id,
                                "matched_line_id": next(x.line_id for x in a.lines if x.code == code),
                                "service_code": code,
                            }
                        )
                    continue
            if NEAR_DUPLICATE_THRESHOLD - 0.01 <= score_hi < NEAR_DUPLICATE_THRESHOLD:
                report.anomalies.append(f"{b.claim_id} vs {a.claim_id} scores {score_hi:.3f}, near the threshold")
            if score_hi >= NEAR_DUPLICATE_THRESHOLD:
                amount = sum((x.amount for x in b.lines if x.code in codes_a), ZERO)
                report.near_scores[(b.claim_id, a.claim_id)] = (score_lo, score_hi)
                report.findings.append(_dup("near_duplicate", "NEAR_DUPLICATE", b, amount, matched_claim_id=a.claim_id))


def check(rows: dict[str, list[Row]]) -> Report:
    report = Report()
    policies, claims = validate(rows, report)
    evaluate_policies(policies, claims, report)
    evaluate_duplicates(claims, report)
    return report


FINDING_KEYS = (
    "category",
    "check_code",
    "match_type",
    "claim_id",
    "line_id",
    "policy_rule_id",
    "matched_claim_id",
    "expected_amount",
)


def verify(rows: dict[str, list[Row]], key: dict[str, Any]) -> list[str]:
    """Recompute everything from rows and return the differences with the answer key (empty list = verified)."""
    report = check(rows)
    problems = list(report.anomalies)

    def project(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[tuple[Any, ...]]:
        return sorted(tuple(item.get(k) for k in keys) for item in items)

    expected = project(key["findings"], FINDING_KEYS)
    found = project(report.findings, FINDING_KEYS)
    for item in sorted(set(expected) - set(found)):
        problems.append(f"finding in key but not recomputed: {item}")
    for item in sorted(set(found) - set(expected)):
        problems.append(f"recomputed finding missing from key: {item}")
    if len(expected) != len(found):
        problems.append(f"finding counts differ: key {len(expected)}, recomputed {len(found)}")

    legit_keys = ("claim_id", "line_id", "matched_claim_id", "matched_line_id", "service_code")
    if project(key["legitimate_repeats"], legit_keys) != project(report.legit, legit_keys):
        problems.append("legitimate repeats differ from the recomputed cleared pairs")

    issue_keys = ("dataset", "row_index", "record_id", "error_code", "severity", "field")
    reported = [i for i in report.issues if i["severity"] == "error" or i["error_code"] == "requested_amount_mismatch"]
    if project(key["invalid_rows"], issue_keys) != project(reported, issue_keys):
        missing = set(project(key["invalid_rows"], issue_keys)) - set(project(reported, issue_keys))
        extra = set(project(reported, issue_keys)) - set(project(key["invalid_rows"], issue_keys))
        problems.append(f"invalid rows differ: key-only {sorted(missing)[:5]}, recomputed-only {sorted(extra)[:5]}")
    if report.accepted != key["accepted_counts"]:
        problems.append(f"accepted counts differ: {report.accepted} vs {key['accepted_counts']}")

    for f in key["findings"]:
        if f["match_type"] == "near_duplicate":
            low, _ = report.near_scores.get((f["claim_id"], f["matched_claim_id"]), (0.0, 0.0))
            if low < NEAR_DUPLICATE_THRESHOLD:
                problems.append(f"near duplicate {f['claim_id']} scores {low:.3f} under a stricter reading")
    return problems
