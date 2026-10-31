"""Typed records the builder produces before they are rendered to file rows."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.core.money import q2
from scripts.datagen.common import ZERO, Provider, service_codes


@dataclass
class Rule:
    rule_id: str
    policy_number: str
    rule_type: str
    scope_type: str
    scope_value: str
    limit_basis: str | None
    limit_amount: Decimal | None
    clause_ref: str
    description: str | None


@dataclass(eq=False)
class Policy:
    number: str
    holder_name: str
    members: list[str]
    member_names: dict[str, str]
    product: str
    start: date
    end: date
    overall_limit: Decimal
    deductible: Decimal
    basis: str
    copay: int
    kind: str = "general"  # general, per_period (dedicated scenario policy) or overall (dedicated)
    rules: list[Rule] = field(default_factory=list)
    room_rule: Rule | None = None
    diag_rule: Rule | None = None
    physio_rule: Rule | None = None
    exclusions: dict[str, Rule] = field(default_factory=dict)
    covered_claim_types: set[str] = field(default_factory=set)
    covered_categories: set[str] = field(default_factory=set)
    split: date | None = None  # per-period deductible policies: settled claims before, open claims after
    budget_used: Decimal = ZERO
    physio_used: Decimal = ZERO
    incident_dates: set[date] = field(default_factory=set)

    @property
    def budget(self) -> Decimal:
        return q2(self.overall_limit * Decimal("0.45"))

    @property
    def budget_left(self) -> Decimal:
        return self.budget - self.budget_used


@dataclass(eq=False)
class Line:
    code: str
    service_date: date
    qty: Decimal
    unit_price: Decimal
    invoice_ref: str
    provider: Provider
    line_id: str = ""

    @property
    def amount(self) -> Decimal:
        return q2(self.qty * self.unit_price)

    @property
    def category(self) -> str:
        return service_codes()[self.code].category

    @property
    def description(self) -> str:
        return service_codes()[self.code].description

    def copy(self, **changes: object) -> "Line":
        values = {
            "code": self.code,
            "service_date": self.service_date,
            "qty": self.qty,
            "unit_price": self.unit_price,
            "invoice_ref": self.invoice_ref,
            "provider": self.provider,
        }
        values.update(changes)
        return Line(**values)  # type: ignore[arg-type]


@dataclass(eq=False)
class Settlement:
    settlement_date: date
    approved: Decimal
    paid: Decimal
    status: str
    settlement_id: str = ""


@dataclass(eq=False)
class Claim:
    policy: Policy
    claimant_id: str
    claimant_name: str
    incident_date: date
    submission_date: date
    claim_type: str
    status: str
    lines: list[Line]
    incident_ref: str | None
    seq: int
    tag: str = "clean"
    requested_override: Decimal | None = None
    settlement: Settlement | None = None
    claim_id: str = ""

    @property
    def line_total(self) -> Decimal:
        return sum((line.amount for line in self.lines), ZERO)

    @property
    def requested(self) -> Decimal:
        return self.requested_override if self.requested_override is not None else self.line_total

    @property
    def provider(self) -> Provider:
        return self.lines[0].provider

    @property
    def first_date(self) -> date:
        return min([self.incident_date, *(line.service_date for line in self.lines)])

    @property
    def last_date(self) -> date:
        return max([self.incident_date, *(line.service_date for line in self.lines)])
