from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.errors import not_found
from app.db.models import Alert, Claim, Document, DuplicateMatch, LineItem, PayableStep, Policy, PolicyRule, Settlement
from app.db.models import ValidationResult as ValidationResultRow
from app.db.session import SessionDep
from app.rules.checks import CHECKS

router = APIRouter(prefix="/claims", tags=["claims"])


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceRow(BaseModel):
    file_name: str | None = None
    sheet: str | None = None
    row_number: int | None = None
    extra: dict[str, Any] | None = None


class LineOut(Orm):
    line_id: str
    invoice_reference: str
    provider_id: str
    provider_name: str
    service_date: date
    service_code: str
    service_description: str
    category: str
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal
    source_row: SourceRow | None


class PolicyRuleOut(Orm):
    rule_id: str
    rule_type: str
    scope_type: str
    scope_value: str
    limit_basis: str | None
    limit_amount: Decimal | None
    clause_ref: str
    description: str | None
    source_row: SourceRow | None


class PolicyOut(Orm):
    policy_number: str
    policyholder_name: str
    insured_member_ids: list[str]
    product_name: str
    benefit_period_start: date
    benefit_period_end: date
    overall_limit: Decimal
    deductible_amount: Decimal
    deductible_basis: str
    copay_percent: Decimal
    source_row: SourceRow | None
    rules: list[PolicyRuleOut] = []


class SettlementOut(Orm):
    settlement_id: str
    settlement_date: date
    approved_amount: Decimal
    paid_amount: Decimal
    settlement_status: str
    source_row: SourceRow | None


class ResultOut(Orm):
    id: int
    check_code: str
    check_name: str = ""
    line_id: str | None
    policy_rule_id: str | None
    outcome: str
    expected: str | None
    actual: str | None
    amount_impact: Decimal
    inputs: dict[str, Any] | None
    explanation: str


class StepOut(Orm):
    step_no: int
    step_code: str
    amount_before: Decimal
    amount_after: Decimal
    reduction: Decimal
    policy_rule_id: str | None
    explanation: str


class MatchOut(Orm):
    id: int
    claim_id: str
    line_id: str | None
    matched_claim_id: str
    matched_line_id: str | None
    matched_source: str
    match_type: str
    score: Decimal | None
    signals: dict[str, Any] | None
    decision: str
    reason: str


class AlertBrief(Orm):
    id: int
    category: str
    severity: str
    amount: Decimal | None
    amount_type: str
    rule_or_pattern: str
    line_id: str | None
    status: str
    explanation: str


class ClaimOut(Orm):
    claim_id: str
    policy_number: str
    claimant_id: str
    claimant_name: str
    incident_date: date
    submission_date: date
    claim_type: str
    requested_amount: Decimal
    incident_reference: str | None
    status: str
    source: str
    import_batch_id: int | None
    source_row: SourceRow | None
    document_id: int | None = None
    payable: Decimal | None = None


class ClaimDetail(BaseModel):
    claim: ClaimOut
    policy: PolicyOut
    lines: list[LineOut]
    settlement: SettlementOut | None
    results: list[ResultOut]
    payable_steps: list[StepOut]
    duplicates: list[MatchOut]
    alerts: list[AlertBrief]


async def claim_detail(session: Any, claim_id: str) -> ClaimDetail:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise not_found("Claim")
    policy = await session.get(Policy, claim.policy_number)
    rules = await session.scalars(
        select(PolicyRule).where(PolicyRule.policy_number == claim.policy_number).order_by(PolicyRule.rule_id)
    )
    lines = await session.scalars(select(LineItem).where(LineItem.claim_id == claim_id).order_by(LineItem.line_id))
    settlement = await session.scalar(select(Settlement).where(Settlement.claim_id == claim_id))
    results = list(
        await session.scalars(
            select(ValidationResultRow)
            .where(ValidationResultRow.claim_id == claim_id)
            .order_by(ValidationResultRow.check_code, ValidationResultRow.id)
        )
    )
    steps = list(
        await session.scalars(select(PayableStep).where(PayableStep.claim_id == claim_id).order_by(PayableStep.step_no))
    )
    matches = await session.scalars(
        select(DuplicateMatch)
        .where((DuplicateMatch.claim_id == claim_id) | (DuplicateMatch.matched_claim_id == claim_id))
        .order_by(DuplicateMatch.id)
    )
    alerts = await session.scalars(select(Alert).where(Alert.claim_id == claim_id).order_by(Alert.id))
    document_id = await session.scalar(select(Document.id).where(Document.claim_id == claim_id).limit(1))
    claim_out = ClaimOut.model_validate(claim)
    claim_out.document_id = document_id
    claim_out.payable = steps[-1].amount_after if steps else None
    policy_out = PolicyOut.model_validate(policy)
    policy_out.rules = [PolicyRuleOut.model_validate(r) for r in rules]
    result_out = [ResultOut.model_validate(r) for r in results]
    for r in result_out:
        r.check_name = CHECKS.get(r.check_code, "")
    return ClaimDetail(
        claim=claim_out,
        policy=policy_out,
        lines=[LineOut.model_validate(ln) for ln in lines],
        settlement=SettlementOut.model_validate(settlement) if settlement else None,
        results=result_out,
        payable_steps=[StepOut.model_validate(s) for s in steps],
        duplicates=[MatchOut.model_validate(m) for m in matches],
        alerts=[AlertBrief.model_validate(a) for a in alerts],
    )


@router.get("/{claim_id}")
async def get_claim(claim_id: str, session: SessionDep) -> ClaimDetail:
    return await claim_detail(session, claim_id)
