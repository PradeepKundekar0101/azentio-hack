"""Plain data the rule engine works on. No database access happens inside checks."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.core.enums import Outcome

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class PolicyData:
    policy_number: str
    insured_member_ids: tuple[str, ...]
    benefit_period_start: date
    benefit_period_end: date
    overall_limit: Decimal
    deductible_amount: Decimal
    deductible_basis: str
    copay_percent: Decimal


@dataclass(frozen=True)
class RuleData:
    rule_id: str
    rule_type: str
    scope_type: str
    scope_value: str
    limit_basis: str | None
    limit_amount: Decimal | None
    clause_ref: str

    @property
    def label(self) -> str:
        return f"rule {self.rule_id}, {self.clause_ref}"


@dataclass(frozen=True)
class LineData:
    line_id: str
    service_date: date
    service_code: str
    service_description: str
    category: str
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal


@dataclass(frozen=True)
class SettlementData:
    settlement_id: str
    settlement_date: date
    approved_amount: Decimal
    paid_amount: Decimal
    settlement_status: str


@dataclass(frozen=True)
class ClaimData:
    claim_id: str
    claimant_id: str
    incident_date: date
    submission_date: date
    claim_type: str
    requested_amount: Decimal
    status: str
    lines: tuple[LineData, ...]
    settlement: SettlementData | None = None


@dataclass
class PolicyLedger:
    """What earlier claims of the same policy already used in the benefit period."""

    deductible_used: Decimal = ZERO
    overall_used: Decimal = ZERO
    sub_limit_used: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))


@dataclass(frozen=True)
class ClaimContext:
    claim: ClaimData
    policy: PolicyData
    rules: tuple[RuleData, ...]
    ledger: PolicyLedger

    def rules_of(self, rule_type: str) -> list[RuleData]:
        return [r for r in self.rules if r.rule_type == rule_type]


@dataclass
class Result:
    """One evaluated check: every check records its outcome, including passes."""

    check_code: str
    outcome: Outcome
    explanation: str
    amount_impact: Decimal = ZERO
    line_id: str | None = None
    policy_rule_id: str | None = None
    expected: str | None = None
    actual: str | None = None
    inputs: dict | None = None


@dataclass
class Step:
    step_code: str
    amount_before: Decimal
    amount_after: Decimal
    explanation: str
    policy_rule_id: str | None = None

    @property
    def reduction(self) -> Decimal:
        return self.amount_before - self.amount_after


@dataclass
class Evaluation:
    claim_id: str
    results: list[Result]
    steps: list[Step]
    payable: Decimal
