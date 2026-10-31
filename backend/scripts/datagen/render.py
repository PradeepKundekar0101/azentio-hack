"""Turns the typed dataset into file rows (mixed date and amount formats), plants invalid rows, writes CSV/XLSX/JSON."""

import csv
import io
import json
import random
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from app.core.money import inr, q2
from scripts.datagen.builder import BuildResult
from scripts.datagen.common import DATASETS, ID_FIELDS, TODAY, parse_date, providers
from scripts.datagen.investigation import investigation_key
from scripts.datagen.model import Claim, Line, Policy, Rule, Settlement


class Num(str):
    """A cell that the JSON export writes as a number; CSV and Excel write the same text."""


Cell = str | None | list[str]
Row = dict[str, Cell]

COLUMNS = {
    "policies": [
        "policy_number", "policyholder_name", "insured_member_ids", "product_name", "benefit_period_start",
        "benefit_period_end", "overall_limit", "deductible_amount", "deductible_basis", "copay_percent",
    ],
    "policy_rules": [
        "rule_id", "policy_number", "rule_type", "scope_type", "scope_value", "limit_basis", "limit_amount",
        "clause_ref", "description",
    ],
    "claims": [
        "claim_id", "policy_number", "claimant_id", "claimant_name", "incident_date", "submission_date", "claim_type",
        "requested_amount", "incident_reference", "status",
    ],
    "line_items": [
        "line_id", "claim_id", "invoice_reference", "provider_id", "provider_name", "service_date", "service_code",
        "service_description", "category", "quantity", "unit_price", "line_amount",
    ],
    "settlements": [
        "settlement_id", "claim_id", "settlement_date", "approved_amount", "paid_amount", "settlement_status",
    ],
}  # fmt: skip

# Header spellings per format. Every header compacts (lowercase, letters and digits only) to the canonical field
# name or one of the importer's accepted synonyms.
HEADERS = {
    "csv": {
        "policies": [
            "Policy No", "Policyholder Name", "Insured Members", "Product", "Benefit Period Start",
            "Benefit Period End", "Sum Insured", "Deductible", "Deductible Basis", "Copay %",
        ],
        "policy_rules": [
            "Rule No", "Policy Number", "Rule Type", "Scope Type", "Scope Value", "Limit Basis", "Limit Amount",
            "Clause", "Description",
        ],
        "claims": [
            "Claim No", "Policy Number", "Member ID", "Claimant Name", "Incident Date", "Submission Date",
            "Claim Type", "Claim Amount", "Incident Ref", "Status",
        ],
        "line_items": [
            "Line ID", "Claim ID", "Invoice No", "Provider ID", "Hospital Name", "Service Date", "Service Code",
            "Service Description", "Category", "Qty", "Unit Price", "Line Amount",
        ],
        "settlements": ["Settlement No", "Claim No", "Settlement Date", "Approved", "Amount Paid", "Status"],
    },
    "xlsx": {
        "policies": [
            "PolicyNumber", "PolicyHolder", "MemberIDs", "Plan", "CoverStart", "CoverEnd", "OverallLimit",
            "DeductibleAmount", "DeductibleType", "CopayPct",
        ],
        "policy_rules": [
            "RuleID", "PolicyNumber", "RuleType", "ScopeType", "ScopeValue", "LimitBasis", "LimitAmount",
            "ClauseReference", "Description",
        ],
        "claims": [
            "ClaimID", "PolicyNo", "ClaimantID", "PatientName", "DateOfIncident", "DateOfSubmission", "ClaimType",
            "RequestedAmount", "IncidentReference", "ClaimStatus",
        ],
        "line_items": [
            "LineItemID", "ClaimID", "InvoiceNumber", "ProviderCode", "ProviderName", "DateOfService",
            "ProcedureCode", "Description", "ServiceCategory", "Quantity", "Rate", "Amount",
        ],
        "settlements": [
            "SettlementID", "ClaimID", "SettlementDate", "ApprovedAmount", "PaidAmount", "SettlementStatus",
        ],
    },
    "json": {
        "policies": [
            "policy_number", "policyholder_name", "insured_member_ids", "product_name", "period start", "period end",
            "overall_limit", "deductible_amount", "deductible_basis", "copay_percent",
        ],
        "policy_rules": COLUMNS["policy_rules"],
        "claims": [
            "claim id", "policy_number", "claimant_id", "claimant name", "incident_date", "submission_date",
            "claim_type", "amount claimed", "incident_reference", "status",
        ],
        "line_items": [
            "line_id", "claim_id", "invoice ref", "provider_id", "provider_name", "service_date", "service_code",
            "service_description", "category", "units", "unit rate", "line total",
        ],
        "settlements": ["settlement_id", "claim_id", "settlement date", "approved_amount", "paid", "settlement_status"],
    },
}  # fmt: skip
SHEETS = {
    "policies": "Policies",
    "policy_rules": "Policy Rules",
    "claims": "Claims",
    "line_items": "Line Items",
    "settlements": "Settlements",
}

INVALID_PLAN = {
    "policies": {
        "missing_field": 3, "negative_amount": 2, "invalid_date": 2, "ambiguous_date": 2, "duplicate_id_in_file": 2,
    },
    "policy_rules": {"missing_field": 6, "negative_amount": 5, "unknown_policy": 8, "duplicate_id_in_file": 6},
    "claims": {
        "missing_field": 10, "negative_amount": 8, "invalid_date": 8, "ambiguous_date": 8,
        "submission_before_incident": 25, "unknown_policy": 20, "duplicate_id_in_file": 8,
    },
    "line_items": {
        "missing_field": 12, "invalid_date": 10, "ambiguous_date": 10, "unknown_claim": 25,
        "line_amount_mismatch": 30, "duplicate_id_in_file": 12, "unknown_service_code": 25,
    },
    "settlements": {
        "missing_field": 5, "negative_amount": 6, "invalid_date": 5, "ambiguous_date": 5, "unknown_claim": 10,
        "duplicate_id_in_file": 5,
    },
}  # fmt: skip
DEMO_INVALID_PLAN = {
    "policies": {},
    "policy_rules": {"missing_field": 1},
    "claims": {"negative_amount": 1, "ambiguous_date": 1},
    "line_items": {"unknown_claim": 1, "line_amount_mismatch": 1, "unknown_service_code": 1},
    "settlements": {"duplicate_id_in_file": 1},
}
INVALID_DATES = ("31-02-2026", "2026-02-30", "31/04/2026", "2026/05/14", "14.05.2026", "May 14 2026", "tomorrow")
UNKNOWN_CODES = (
    ("DX-PETCT", "PET-CT scan", "diagnostics"),
    ("PRC-ROBO", "Robotic surgery assistance", "procedure"),
    ("CON-HOME", "Home visit consultation", "consultation"),
    ("PHA-HERB", "Herbal preparation", "pharmacy"),
    ("OTH-SPA", "Wellness spa package", "other"),
)


# ---- cell formatting ---------------------------------------------------------------------------------------


def fmt_date(value: date, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.5:
        return value.isoformat()
    separator = "-" if roll < 0.75 else "/"
    if rng.random() < 0.1:
        return f"{value.day}{separator}{value.month}{separator}{value.year}"
    return f"{value.day:02d}{separator}{value.month:02d}{separator}{value.year}"


def two_digit_year(value: date, rng: random.Random) -> str:
    separator = rng.choice("-/")
    return f"{value.day:02d}{separator}{value.month:02d}{separator}{value.year % 100:02d}"


def plain_amount(value: Decimal) -> str:
    value = q2(value)
    if value == value.to_integral_value():
        return str(int(value))
    text = f"{value:.2f}"
    return text[:-1] if text.endswith("0") else text


def fmt_amount(value: Decimal, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.5:
        text = plain_amount(value)
        return Num(text) if rng.random() < 0.5 else text
    if roll < 0.75:
        return inr(value).replace("₹", "")
    return inr(value)


def fmt_number(value: Decimal | int, rng: random.Random) -> str:
    text = plain_amount(Decimal(value))
    return Num(text) if rng.random() < 0.5 else text


# ---- typed records to rows ---------------------------------------------------------------------------------


@dataclass
class Tag:
    error_code: str
    field: str | None
    severity: str = "error"


@dataclass
class Renderer:
    result: BuildResult
    seed: int
    scale: float
    demo: bool
    rng: random.Random = field(init=False)
    rows: dict[str, list[Row]] = field(default_factory=lambda: {ds: [] for ds in DATASETS})
    tags: dict[int, Tag] = field(default_factory=dict)  # id(row) -> planted issue

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed * 7919 + 17)
        ids = self.result.builder.ids
        self.junk_base = ids
        self.junk_seq = 0

    def policy_row(self, p: Policy) -> Row:
        r = self.rng
        return {
            "policy_number": p.number,
            "policyholder_name": p.holder_name,
            "insured_member_ids": list(p.members),
            "product_name": p.product,
            "benefit_period_start": fmt_date(p.start, r),
            "benefit_period_end": fmt_date(p.end, r),
            "overall_limit": fmt_amount(p.overall_limit, r),
            "deductible_amount": fmt_amount(p.deductible, r),
            "deductible_basis": p.basis,
            "copay_percent": fmt_number(p.copay, r),
        }

    def rule_row(self, rule: Rule) -> Row:
        return {
            "rule_id": rule.rule_id,
            "policy_number": rule.policy_number,
            "rule_type": rule.rule_type,
            "scope_type": rule.scope_type,
            "scope_value": rule.scope_value,
            "limit_basis": rule.limit_basis,
            "limit_amount": fmt_amount(rule.limit_amount, self.rng) if rule.limit_amount is not None else None,
            "clause_ref": rule.clause_ref,
            "description": rule.description,
        }

    def claim_row(self, c: Claim) -> Row:
        r = self.rng
        return {
            "claim_id": c.claim_id,
            "policy_number": c.policy.number,
            "claimant_id": c.claimant_id,
            "claimant_name": c.claimant_name,
            "incident_date": fmt_date(c.incident_date, r),
            "submission_date": fmt_date(c.submission_date, r),
            "claim_type": c.claim_type,
            "requested_amount": fmt_amount(c.requested, r),
            "incident_reference": c.incident_ref,
            "status": c.status,
        }

    def line_row(self, line: Line, claim_id: str) -> Row:
        r = self.rng
        return {
            "line_id": line.line_id,
            "claim_id": claim_id,
            "invoice_reference": line.invoice_ref,
            "provider_id": line.provider.provider_id,
            "provider_name": line.provider.name,
            "service_date": fmt_date(line.service_date, r),
            "service_code": line.code,
            "service_description": line.description,
            "category": line.category,
            "quantity": fmt_number(line.qty, r),
            "unit_price": fmt_amount(line.unit_price, r),
            "line_amount": fmt_amount(line.amount, r),
        }

    def settlement_row(self, s: Settlement, claim_id: str) -> Row:
        r = self.rng
        return {
            "settlement_id": s.settlement_id,
            "claim_id": claim_id,
            "settlement_date": fmt_date(s.settlement_date, r),
            "approved_amount": fmt_amount(s.approved, r),
            "paid_amount": fmt_amount(s.paid, r),
            "settlement_status": s.status,
        }

    def render_valid(self) -> None:
        for policy in self.result.policies:
            self.rows["policies"].append(self.policy_row(policy))
            for rule in policy.rules:
                self.rows["policy_rules"].append(self.rule_row(rule))
        for claim in self.result.claims:
            row = self.claim_row(claim)
            self.rows["claims"].append(row)
            if claim in self.result.mismatched:
                self.tags[id(row)] = Tag("requested_amount_mismatch", "requested_amount", "warning")
            for line in claim.lines:
                self.rows["line_items"].append(self.line_row(line, claim.claim_id))
        for claim in self.result.claims:
            if claim.settlement is not None:
                self.rows["settlements"].append(self.settlement_row(claim.settlement, claim.claim_id))

    # ---- planted invalid rows --------------------------------------------------------------------------------

    def insert(self, dataset: str, row: Row, tag: Tag, after: Row | None = None) -> None:
        rows = self.rows[dataset]
        lo = 0 if after is None else next(i for i, r in enumerate(rows) if r is after) + 1
        rows.insert(self.rng.randint(lo, len(rows)), row)
        self.tags[id(row)] = tag

    def junk_id(self) -> int:
        self.junk_seq += 1
        return self.junk_seq

    def plant_invalid(self) -> None:
        plan = DEMO_INVALID_PLAN if self.demo else INVALID_PLAN
        for dataset in DATASETS:
            for code, count in plan[dataset].items():
                n = count if self.demo else max(1, round(count * self.scale))
                for k in range(n):
                    getattr(self, f"junk_{dataset}")(code, k)
        if not self.demo:
            self.junk_policy_with_children()

    def valid_row(self, dataset: str, predicate: Any = None) -> Row:
        candidates = [r for r in self.rows[dataset] if id(r) not in self.tags and (predicate is None or predicate(r))]
        return self.rng.choice(candidates)

    def date_in(self, policy: Policy) -> date:
        hi = min(policy.end, TODAY - timedelta(days=20))
        return policy.start + timedelta(days=self.rng.randint(0, max(0, (hi - policy.start).days)))

    def junk_policies(self, code: str, k: int) -> None:
        if code == "duplicate_id_in_file":
            original = self.valid_row("policies")
            self.insert("policies", dict(original), Tag(code, "policy_number"), after=original)
            return
        row = self.fresh_policy_row()
        field_name = {
            "missing_field": self.rng.choice(["policyholder_name", "product_name", "deductible_basis"]),
            "negative_amount": self.rng.choice(["overall_limit", "deductible_amount"]),
            "invalid_date": "benefit_period_end",
            "ambiguous_date": "benefit_period_start",
        }[code]
        self.corrupt(row, code, field_name)
        self.insert("policies", row, Tag(code, field_name))

    def fresh_policy_row(self) -> Row:
        b = self.result.builder
        number = f"POL-{self.junk_base.policy + 9000 + self.junk_id():06d}"
        start = date(2025, 9, 1) + timedelta(days=self.rng.randint(0, 200))
        members = [f"MEM-{self.junk_base.member + 90000 + self.junk_id():06d}" for _ in range(2)]
        return {
            "policy_number": number,
            "policyholder_name": b.name(),
            "insured_member_ids": members,
            "product_name": self.rng.choice(["Silver", "Gold", "Platinum"]),
            "benefit_period_start": fmt_date(start, self.rng),
            "benefit_period_end": fmt_date(date(start.year + 1, start.month, start.day) - timedelta(days=1), self.rng),
            "overall_limit": fmt_amount(Decimal(500000), self.rng),
            "deductible_amount": fmt_amount(Decimal(3000), self.rng),
            "deductible_basis": "per_claim",
            "copay_percent": "10",
        }

    def corrupt(self, row: Row, code: str, field_name: str) -> None:
        value = row[field_name]
        if code == "missing_field":
            row[field_name] = None
        elif code == "negative_amount":
            row[field_name] = (
                "-" + str(value).replace("₹", "") if self.rng.random() < 0.5 else "-₹" + str(value).replace("₹", "")
            )
        elif code == "invalid_date":
            row[field_name] = self.rng.choice(INVALID_DATES)
        elif code == "ambiguous_date":
            row[field_name] = two_digit_year(date(2026, self.rng.randint(1, 9), self.rng.randint(1, 28)), self.rng)
        else:
            raise ValueError(code)

    def junk_policy_rules(self, code: str, k: int) -> None:
        if code == "duplicate_id_in_file":
            original = self.valid_row("policy_rules")
            self.insert("policy_rules", dict(original), Tag(code, "rule_id"), after=original)
            return
        policy = self.rng.choice(self.result.policies)
        number = policy.number
        if code == "unknown_policy":
            number = f"POL-{self.junk_base.policy + 50000 + self.junk_id():06d}"
        row: Row = {
            "rule_id": f"{number}-XR-{self.junk_id():02d}",
            "policy_number": number,
            "rule_type": "exclusion",
            "scope_type": "service_code",
            "scope_value": self.rng.choice(["PRC-BARI", "PRC-DENT"]),
            "limit_basis": None,
            "limit_amount": None,
            "clause_ref": "Section 5.6 Bariatric surgery",
            "description": "Added in error.",
        }
        field_name = "policy_number"
        if code == "missing_field":
            field_name = "clause_ref"
            row["clause_ref"] = None
        elif code == "negative_amount":
            field_name = "limit_amount"
            row.update(rule_type="sub_limit", scope_type="category", scope_value="other", limit_basis="per_claim")
            row.update(limit_amount="-5,000", clause_ref="Section 4.9 Other charges limit")
        self.insert("policy_rules", row, Tag(code, field_name))

    def fresh_claim(self, policy_number: str | None = None) -> tuple[Row, list[Row]]:
        b = self.result.builder
        policy = self.rng.choice(self.result.policies)
        member = self.rng.choice(policy.members)
        incident = self.date_in(policy)
        provider = self.rng.choice(providers())
        claim_id = f"CLM-{self.junk_base.claim + 80000 + self.junk_id():06d}"
        lines: list[Row] = []
        total = Decimal(0)
        ref = f"{b.prefix[provider.provider_id]}-{self.junk_base.claim + 70000 + self.junk_id():06d}"
        for code in self.rng.sample(["CON-GP", "PHA-ABX", "DX-CBC", "PHA-ANLG"], self.rng.randint(1, 3)):
            line = b.line(code, incident, 1, provider, ref)
            line.line_id = f"LN-{self.junk_base.line + 900000 + self.junk_id():07d}"
            lines.append(self.line_row(line, claim_id))
            total += line.amount
        row: Row = {
            "claim_id": claim_id,
            "policy_number": policy_number or policy.number,
            "claimant_id": member,
            "claimant_name": policy.member_names[member],
            "incident_date": fmt_date(incident, self.rng),
            "submission_date": fmt_date(incident + timedelta(days=self.rng.randint(2, 10)), self.rng),
            "claim_type": "outpatient",
            "requested_amount": fmt_amount(total, self.rng),
            "incident_reference": None,
            "status": "open",
        }
        return row, lines

    def junk_claims(self, code: str, k: int) -> None:
        if code == "duplicate_id_in_file":
            original = self.valid_row("claims")
            self.insert("claims", dict(original), Tag(code, "claim_id"), after=original)
            return
        unknown = f"POL-{self.junk_base.policy + 50000 + self.junk_id():06d}" if code == "unknown_policy" else None
        row, lines = self.fresh_claim(unknown)
        field_name = "policy_number"
        if code == "missing_field":
            field_name = self.rng.choice(["claimant_name", "claim_type", "status", "claim_id"])
            row[field_name] = None
        elif code == "negative_amount":
            field_name = "requested_amount"
            self.corrupt(row, code, field_name)
        elif code in ("invalid_date", "ambiguous_date"):
            field_name = "incident_date"
            self.corrupt(row, code, field_name)
        elif code == "submission_before_incident":
            field_name = "submission_date"
            incident = date.fromisoformat(self.iso(row["incident_date"]))
            row["submission_date"] = fmt_date(incident - timedelta(days=self.rng.randint(2, 20)), self.rng)
        self.insert("claims", row, Tag(code, field_name))
        if row["claim_id"] is not None and (self.demo or self.rng.random() < 0.6):
            for line in lines:
                self.insert("line_items", line, Tag("parent_rejected", "claim_id"))

    @staticmethod
    def iso(value: Cell) -> str:
        parsed, _ = parse_date(str(value))
        assert parsed is not None
        return parsed.isoformat()

    def clean_claims(self) -> list[Claim]:
        return [c for c in self.result.claims if c.tag == "clean" and c.status == "open"]

    def junk_line_items(self, code: str, k: int) -> None:
        if code == "duplicate_id_in_file":
            original = self.valid_row("line_items")
            self.insert("line_items", dict(original), Tag(code, "line_id"), after=original)
            return
        b = self.result.builder
        claim = self.rng.choice(self.clean_claims())
        line = b.line(
            self.rng.choice(["CS-DRS", "PHA-OTC", "CON-GP"]),
            claim.incident_date,
            1,
            claim.provider,
            claim.lines[0].invoice_ref,
        )
        line.line_id = f"LN-{self.junk_base.line + 900000 + self.junk_id():07d}"
        row = self.line_row(line, claim.claim_id)
        if code == "missing_field":
            field_name = self.rng.choice(["provider_name", "service_description", "invoice_reference", "line_id"])
            row[field_name] = None
        elif code in ("invalid_date", "ambiguous_date"):
            field_name = "service_date"
            self.corrupt(row, code, field_name)
        elif code == "unknown_claim":
            field_name = "claim_id"
            row["claim_id"] = f"CLM-{self.junk_base.claim + 60000 + self.junk_id():06d}"
        elif code == "line_amount_mismatch":
            field_name = "line_amount"
            row["line_amount"] = fmt_amount(line.amount + Decimal(self.rng.choice(range(50, 1001, 50))), self.rng)
        elif code == "unknown_service_code":
            field_name = "service_code"
            unknown, description, category = self.rng.choice(UNKNOWN_CODES)
            row.update(service_code=unknown, service_description=description, category=category)
        else:
            raise ValueError(code)
        self.insert("line_items", row, Tag(code, field_name))

    def junk_settlements(self, code: str, k: int) -> None:
        if code == "duplicate_id_in_file":
            original = self.valid_row("settlements")
            self.insert("settlements", dict(original), Tag(code, "settlement_id"), after=original)
            return
        claim = self.rng.choice([c for c in self.result.claims if c.settlement is not None and c.tag == "clean"])
        when = min(claim.submission_date + timedelta(days=self.rng.randint(5, 30)), TODAY)
        amount = Decimal(self.rng.choice(range(500, 5001, 250)))
        settlement = Settlement(
            when, amount, amount, "paid", f"STL-{self.junk_base.settlement + 80000 + self.junk_id():06d}"
        )
        row = self.settlement_row(settlement, claim.claim_id)
        if code == "missing_field":
            field_name = self.rng.choice(["settlement_status", "approved_amount"])
            row[field_name] = None
        elif code == "negative_amount":
            field_name = "paid_amount"
            self.corrupt(row, code, field_name)
        elif code in ("invalid_date", "ambiguous_date"):
            field_name = "settlement_date"
            self.corrupt(row, code, field_name)
        elif code == "unknown_claim":
            field_name = "claim_id"
            row["claim_id"] = f"CLM-{self.junk_base.claim + 60000 + self.junk_id():06d}"
        else:
            raise ValueError(code)
        self.insert("settlements", row, Tag(code, field_name))

    def junk_policy_with_children(self) -> None:
        """A rejected policy whose rules, claim and lines are rejected in turn ('parent_rejected')."""
        row = self.fresh_policy_row()
        self.corrupt(row, "invalid_date", "benefit_period_end")
        self.insert("policies", row, Tag("invalid_date", "benefit_period_end"))
        number = row["policy_number"]
        for k, category in enumerate(("inpatient", "outpatient"), start=1):
            rule: Row = {
                "rule_id": f"{number}-CV-{k:02d}",
                "policy_number": number,
                "rule_type": "coverage",
                "scope_type": "claim_type",
                "scope_value": category,
                "limit_basis": None,
                "limit_amount": None,
                "clause_ref": f"Section 2.{k} Covered claim types",
                "description": None,
            }
            self.insert("policy_rules", rule, Tag("parent_rejected", "policy_number"))
        claim, lines = self.fresh_claim(str(number))
        members = row["insured_member_ids"]
        assert isinstance(members, list)
        claim["claimant_id"] = members[0]
        claim["claimant_name"] = row["policyholder_name"]
        self.insert("claims", claim, Tag("parent_rejected", "policy_number"))
        for line in lines:
            self.insert("line_items", line, Tag("parent_rejected", "claim_id"))

    # ---- answer key ------------------------------------------------------------------------------------------

    def invalid_rows(self) -> list[dict[str, Any]]:
        out = []
        for dataset in DATASETS:
            for index, row in enumerate(self.rows[dataset]):
                tag = self.tags.get(id(row))
                if tag is None:
                    continue
                record = row.get(ID_FIELDS[dataset])
                out.append(
                    {
                        "dataset": dataset,
                        "row_index": index,
                        "record_id": record if isinstance(record, str) else None,
                        "error_code": tag.error_code,
                        "severity": tag.severity,
                        "field": tag.field,
                    }
                )
        return out

    def answer_key(self, seed: int) -> dict[str, Any]:
        def cid(claim: Claim | None) -> str | None:
            return claim.claim_id if claim is not None else None

        def lid(line: Line | None) -> str | None:
            return line.line_id if line is not None else None

        findings = [
            {
                "scenario": f["scenario"],
                "category": f["category"],
                "check_code": f["check_code"],
                "match_type": f["match_type"],
                "amount_type": f["amount_type"],
                "expected_amount": f"{f['expected_amount']:.2f}",
                "claim_id": cid(f["claim"]),
                "line_id": lid(f["line"]),
                "policy_rule_id": f["policy_rule_id"],
                "matched_claim_id": cid(f["matched_claim"]),
                "matched_line_id": lid(f["matched_line"]),
            }
            for f in self.result.findings
        ]
        findings.sort(key=lambda f: (f["scenario"], f["claim_id"], f["line_id"] or ""))
        legit = sorted(
            (
                {
                    "claim_id": cid(x["claim"]),
                    "line_id": lid(x["line"]),
                    "matched_claim_id": cid(x["matched_claim"]),
                    "matched_line_id": lid(x["matched_line"]),
                    "service_code": x["service_code"],
                }
                for x in self.result.legit
            ),
            key=lambda x: x["claim_id"],
        )
        invalid = self.invalid_rows()
        rejected = {ds: 0 for ds in DATASETS}
        for issue in invalid:
            if issue["severity"] == "error":
                rejected[issue["dataset"]] += 1
        key: dict[str, Any] = {
            "seed": seed,
            "counts": {ds: len(self.rows[ds]) for ds in DATASETS},
            "accepted_counts": {ds: len(self.rows[ds]) - rejected[ds] for ds in DATASETS},
            "findings": findings,
            "legitimate_repeats": legit,
            "invalid_rows": invalid,
        }
        if self.result.investigation is not None:
            key["investigation"] = investigation_key(self.result.investigation, len(legit))
        return key


def render(result: BuildResult, seed: int, scale: float, demo: bool) -> tuple[dict[str, list[Row]], dict[str, Any]]:
    renderer = Renderer(result, seed, scale, demo)
    renderer.render_valid()
    renderer.plant_invalid()
    return renderer.rows, renderer.answer_key(seed)


# ---- writers -----------------------------------------------------------------------------------------------

FIXED_TIME = datetime(2026, 10, 31, 0, 0, 0)


def _text(value: Cell) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return "|".join(value)
    return str(value)


def write_csv(directory: Path, rows: dict[str, list[Row]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for dataset in DATASETS:
        with (directory / f"{dataset}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(HEADERS["csv"][dataset])
            for row in rows[dataset]:
                writer.writerow([_text(row[c]) or "" for c in COLUMNS[dataset]])


def write_xlsx(path: Path, rows: dict[str, list[Row]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook(write_only=True)
    workbook.properties.created = FIXED_TIME
    workbook.properties.modified = FIXED_TIME
    workbook.properties.creator = "generate_data"
    for dataset in DATASETS:
        sheet = workbook.create_sheet(SHEETS[dataset])
        sheet.append(HEADERS["xlsx"][dataset])
        for row in rows[dataset]:
            sheet.append([_text(row[c]) for c in COLUMNS[dataset]])
    buffer = io.BytesIO()
    workbook.save(buffer)
    path.write_bytes(_fixed_zip(buffer.getvalue()))


def _fixed_zip(data: bytes) -> bytes:
    """Rewrite a zip archive with fixed entry timestamps (openpyxl stamps the current time)."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                content = _fix_core(content)
            fixed = zipfile.ZipInfo(info.filename, date_time=(2026, 10, 31, 0, 0, 0))
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = 0o600 << 16
            target.writestr(fixed, content)
    return out.getvalue()


def _fix_core(content: bytes) -> bytes:
    stamp = FIXED_TIME.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    return re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:)", rb"\g<1>" + stamp + rb"\g<2>", content)


def _json_value(value: Cell) -> Any:
    if isinstance(value, Num):
        return int(value) if "." not in value else float(value)
    return value


def write_json(path: Path, rows: dict[str, list[Row]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        dataset: [
            {h: _json_value(row[c]) for h, c in zip(HEADERS["json"][dataset], COLUMNS[dataset], strict=True)}
            for row in rows[dataset]
        ]
        for dataset in DATASETS
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def write_answer_key(path: Path, key: dict[str, Any]) -> None:
    path.write_text(json.dumps(key, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_all(directory: Path, rows: dict[str, list[Row]], key: dict[str, Any]) -> None:
    write_csv(directory / "csv", rows)
    write_xlsx(directory / "xlsx" / "claims_data.xlsx", rows)
    write_json(directory / "json" / "claims_data.json", rows)
    write_answer_key(directory / "answer_key.json", key)
