from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.claims import ClaimDetail, MatchOut, claim_detail
from app.api.filters import FiltersDep
from app.api.pagination import Page, PageDep
from app.core import audit
from app.core.enums import AlertStatus, EscalationTarget, MatchDecision
from app.core.errors import not_found
from app.core.security import CurrentPrincipal, forbidden
from app.db.models import Alert, Claim, DuplicateMatch, LineItem
from app.db.session import SessionDep
from app.evidence import service as evidence

router = APIRouter(tags=["alerts"])


def mask_name(name: str) -> str:
    """'Ravi Kumar' -> 'R*** K***'. Full names are shown only on detail pages."""
    return " ".join(f"{part[0]}***" for part in name.split() if part)


class AlertRow(BaseModel):
    id: int
    claim_id: str
    claimant: str
    provider_id: str | None
    provider_name: str | None
    claim_type: str
    category: str
    severity: str
    amount: Decimal | None
    amount_type: str
    rule_or_pattern: str
    incident_date: date
    status: str


class AlertOut(BaseModel):
    id: int
    finding_id: str
    run_id: int | None
    graph_build_id: int | None
    claim_id: str
    line_id: str | None
    category: str
    severity: str
    amount: Decimal | None
    amount_type: str
    calculation: str | None
    rule_or_pattern: str
    policy_rule_id: str | None
    explanation: str
    supporting: dict[str, Any]
    status: str
    review_note: str | None
    reviewed_at: datetime | None
    reviewed_by: str | None
    escalated_to: str | None
    escalated_by: str | None
    escalated_at: datetime | None
    escalation_reason: str | None
    created_at: datetime


class AlertDetail(BaseModel):
    alert: AlertOut
    claim: ClaimDetail
    matched_claim: ClaimDetail | None
    match: MatchOut | None


class AlertPatch(BaseModel):
    """An analyst's decision on a finding. Dismissing and escalating need a reason; an escalation says
    who should look at it."""

    status: Literal["open", "reviewed", "dismissed", "evidence_requested", "escalated"]
    note: str | None = Field(default=None, max_length=2000)
    escalate_to: EscalationTarget | None = None

    @model_validator(mode="after")
    def _reasons(self) -> "AlertPatch":
        note = (self.note or "").strip()
        if self.status in ("dismissed", "escalated", "evidence_requested") and not note:
            raise ValueError(f"A note is required to mark an alert {self.status.replace('_', ' ')}")
        if self.status == "escalated" and self.escalate_to is None:
            raise ValueError("escalate_to is required when escalating")
        if self.status != "escalated" and self.escalate_to is not None:
            raise ValueError("escalate_to only applies when escalating")
        return self


async def _providers(session: AsyncSession, alerts: list[Alert]) -> dict[int, tuple[str, str]]:
    """Provider of each alert: its line's provider, else the claim's first line's provider."""
    claim_ids = {a.claim_id for a in alerts}
    if not claim_ids:
        return {}
    lines = await session.execute(
        select(LineItem.line_id, LineItem.claim_id, LineItem.provider_id, LineItem.provider_name)
        .where(LineItem.claim_id.in_(claim_ids))
        .order_by(LineItem.line_id)
    )
    by_line, by_claim = {}, {}
    for line_id, claim_id, provider_id, provider_name in lines:
        by_line[line_id] = (provider_id, provider_name)
        by_claim.setdefault(claim_id, (provider_id, provider_name))
    return {a.id: by_line.get(a.line_id or "") or by_claim.get(a.claim_id) for a in alerts}


@router.get("/alerts")
async def list_alerts(
    session: SessionDep,
    page: PageDep,
    filters: FiltersDep,
    sort: Annotated[str, Query(pattern=r"^-?(id|amount|severity|incident_date|category|claim_id|status)$")] = "-amount",
) -> Page[AlertRow]:
    query = filters.alerts()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    column = {
        "id": Alert.id,
        "amount": Alert.amount,
        "severity": func.array_position(func.string_to_array("critical,high,medium,low,review", ","), Alert.severity),
        "incident_date": Claim.incident_date,
        "category": Alert.category,
        "claim_id": Alert.claim_id,
        "status": Alert.status,
    }[sort.lstrip("-")]
    descending = sort.startswith("-")
    if sort.lstrip("-") == "severity":
        descending = not descending  # rank 1 is the most severe
    order = column.desc().nulls_last() if descending else column.asc().nulls_last()
    rows = (
        await session.execute(
            query.add_columns(Claim).order_by(order, Alert.id).offset(page.offset).limit(page.page_size)
        )
    ).all()
    alerts = [row[0] for row in rows]
    providers = await _providers(session, alerts)
    items = []
    for alert, claim in rows:
        provider = providers.get(alert.id) or (None, None)
        items.append(
            AlertRow(
                id=alert.id,
                claim_id=alert.claim_id,
                claimant=mask_name(claim.claimant_name),
                provider_id=provider[0],
                provider_name=provider[1],
                claim_type=claim.claim_type,
                category=alert.category,
                severity=alert.severity,
                amount=alert.amount,
                amount_type=alert.amount_type,
                rule_or_pattern=alert.rule_or_pattern,
                incident_date=claim.incident_date,
                status=alert.status,
            )
        )
    return Page(items=items, total=total or 0)


async def _alert_detail(session: AsyncSession, alert: Alert) -> AlertDetail:
    claim = await claim_detail(session, alert.claim_id)
    matched_id = (alert.supporting or {}).get("matched_claim_id")
    matched = await claim_detail(session, matched_id) if matched_id and matched_id != alert.claim_id else None
    match = (
        next(
            (
                m
                for m in claim.duplicates
                if m.claim_id == alert.claim_id and m.matched_claim_id == matched_id and (m.line_id == alert.line_id)
            ),
            None,
        )
        if matched_id
        else None
    )
    return AlertDetail(
        alert=AlertOut.model_validate(alert, from_attributes=True), claim=claim, matched_claim=matched, match=match
    )


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int, session: SessionDep) -> AlertDetail:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise not_found("Alert")
    return await _alert_detail(session, alert)


@router.patch("/alerts/{alert_id}")
async def update_alert(alert_id: int, body: AlertPatch, session: SessionDep, principal: CurrentPrincipal) -> AlertOut:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise not_found("Alert")
    if alert.status == AlertStatus.ESCALATED.value:
        # An escalated alert is decided by a senior claims reviewer or an admin, and never by the
        # person who escalated it: the pack's "authorised workflow" means a second pair of eyes.
        if not principal.can_decide_escalations():
            raise forbidden("Escalated alerts are decided by a senior claims reviewer")
        if alert.escalated_by == principal.username:
            raise forbidden("Someone else must decide an alert you escalated")
    now = datetime.now(UTC)
    note = (body.note or "").strip() or None
    audit.record(
        session,
        principal.username,
        "alert_status_changed",
        "alert",
        alert.id,
        previous=alert.status,
        status=body.status,
        note=note,
        actor_role=principal.role,
        escalate_to=body.escalate_to.value if body.escalate_to else None,
        previous_escalation=(
            {"to": alert.escalated_to, "by": alert.escalated_by, "reason": alert.escalation_reason}
            if alert.escalated_to
            else None
        ),
    )
    previous = alert.status
    alert.status = body.status
    alert.review_note = note
    alert.reviewed_at = None if body.status == AlertStatus.OPEN.value else now
    alert.reviewed_by = None if body.status == AlertStatus.OPEN.value else principal.username
    if body.status == AlertStatus.ESCALATED.value and body.escalate_to is not None:
        alert.escalated_to = body.escalate_to.value
        alert.escalated_by = principal.username
        alert.escalated_at = now
        alert.escalation_reason = note
    else:
        # The decision closes the escalation; the audit log keeps who asked for it and why.
        alert.escalated_to = alert.escalated_by = alert.escalated_at = alert.escalation_reason = None
    await evidence.record_decision(
        session,
        alert,
        principal.username,
        previous,
        note,
        actor_role=principal.role,
        extra={"escalate_to": body.escalate_to.value if body.escalate_to else None},
    )
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert, from_attributes=True)


class ClearedRow(BaseModel):
    id: int
    claim_id: str
    line_id: str | None
    matched_claim_id: str
    matched_line_id: str | None
    claimant: str
    service_code: str | None
    service_description: str | None
    reason: str
    signals: dict[str, Any] | None


@router.get("/duplicates/cleared")
async def cleared_duplicates(session: SessionDep, page: PageDep) -> Page[ClearedRow]:
    query = select(DuplicateMatch).where(DuplicateMatch.decision == MatchDecision.CLEARED.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.execute(
            query.add_columns(Claim, LineItem)
            .join(Claim, Claim.claim_id == DuplicateMatch.claim_id)
            .outerjoin(LineItem, LineItem.line_id == DuplicateMatch.line_id)
            .order_by(DuplicateMatch.id)
            .offset(page.offset)
            .limit(page.page_size)
        )
    ).all()
    return Page(
        items=[
            ClearedRow(
                id=m.id,
                claim_id=m.claim_id,
                line_id=m.line_id,
                matched_claim_id=m.matched_claim_id,
                matched_line_id=m.matched_line_id,
                claimant=mask_name(c.claimant_name),
                service_code=ln.service_code if ln else None,
                service_description=ln.service_description if ln else None,
                reason=m.reason,
                signals=m.signals,
            )
            for m, c, ln in rows
        ],
        total=total or 0,
    )
