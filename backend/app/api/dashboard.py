"""KPIs and breakdowns. Accepts the same filters as /alerts. Calculated and estimated leakage stay separate."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import distinct, func, select

from app.api.filters import FiltersDep
from app.core.enums import AlertStatus, AmountType
from app.db.models import Claim, LineItem, ProcessingRun, ValidationResult
from app.db.session import SessionDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
ZERO = Decimal("0")


class Kpis(BaseModel):
    claims_processed: int
    flagged_claims: int
    flagged_percent: Decimal
    open_alerts: int
    calculated_leakage: Decimal
    estimated_leakage: Decimal
    suspected_alerts: int


class CategoryRow(BaseModel):
    category: str
    alerts: int
    calculated_amount: Decimal
    estimated_amount: Decimal


class SeverityRow(BaseModel):
    severity: str
    alerts: int


class ProviderRow(BaseModel):
    provider_id: str
    provider_name: str
    calculated_amount: Decimal
    alerts: int


class LastRun(BaseModel):
    id: int
    status: str
    scope: str
    started_at: datetime
    finished_at: datetime | None
    claims_processed: int


class Summary(BaseModel):
    kpis: Kpis
    by_category: list[CategoryRow]
    by_severity: list[SeverityRow]
    top_providers: list[ProviderRow]
    last_run: LastRun | None


@router.get("/summary")
async def summary(session: SessionDep, filters: FiltersDep) -> Summary:
    alerts = filters.alerts().subquery()
    claims_processed = await session.scalar(
        select(func.count(distinct(Claim.claim_id)))
        .join(ValidationResult, ValidationResult.claim_id == Claim.claim_id)
        .where(*filters.claim_conditions())
    )
    totals = (
        await session.execute(
            select(
                func.count(distinct(alerts.c.claim_id)),
                func.count().filter(alerts.c.status == AlertStatus.OPEN.value),
                func.coalesce(
                    func.sum(alerts.c.amount).filter(alerts.c.amount_type == AmountType.CALCULATED.value), ZERO
                ),
                func.coalesce(
                    func.sum(alerts.c.amount).filter(alerts.c.amount_type == AmountType.ESTIMATED.value), ZERO
                ),
                func.count().filter(alerts.c.amount_type == AmountType.SUSPECTED.value),
            ).select_from(alerts)
        )
    ).one()
    flagged, open_alerts, calculated, estimated, suspected = totals
    processed = claims_processed or 0
    percent = (Decimal(flagged) * 100 / processed).quantize(Decimal("0.1")) if processed else ZERO

    by_category = [
        CategoryRow(category=c, alerts=n, calculated_amount=calc, estimated_amount=est)
        for c, n, calc, est in await session.execute(
            select(
                alerts.c.category,
                func.count(),
                func.coalesce(
                    func.sum(alerts.c.amount).filter(alerts.c.amount_type == AmountType.CALCULATED.value), ZERO
                ),
                func.coalesce(
                    func.sum(alerts.c.amount).filter(alerts.c.amount_type == AmountType.ESTIMATED.value), ZERO
                ),
            )
            .group_by(alerts.c.category)
            .order_by(func.count().desc())
        )
    ]
    by_severity = [
        SeverityRow(severity=s, alerts=n)
        for s, n in await session.execute(select(alerts.c.severity, func.count()).group_by(alerts.c.severity))
    ]
    # Provider of an alert: its line's provider, else the claim's first line (lowest line id).
    first_line = (
        select(LineItem.claim_id, func.min(LineItem.line_id).label("line_id")).group_by(LineItem.claim_id).subquery()
    )
    provider_line = func.coalesce(alerts.c.line_id, first_line.c.line_id)
    top = await session.execute(
        select(
            LineItem.provider_id,
            func.min(LineItem.provider_name),
            func.coalesce(func.sum(alerts.c.amount), ZERO),
            func.count(),
        )
        .select_from(alerts)
        .join(first_line, first_line.c.claim_id == alerts.c.claim_id)
        .join(LineItem, LineItem.line_id == provider_line)
        .where(alerts.c.amount_type == AmountType.CALCULATED.value)
        .group_by(LineItem.provider_id)
        .order_by(func.sum(alerts.c.amount).desc())
        .limit(10)
    )
    run = await session.scalar(select(ProcessingRun).order_by(ProcessingRun.id.desc()).limit(1))
    return Summary(
        kpis=Kpis(
            claims_processed=processed,
            flagged_claims=flagged,
            flagged_percent=percent,
            open_alerts=open_alerts,
            calculated_leakage=calculated,
            estimated_leakage=estimated,
            suspected_alerts=suspected,
        ),
        by_category=by_category,
        by_severity=by_severity,
        top_providers=[
            ProviderRow(provider_id=p, provider_name=name, calculated_amount=amount, alerts=n)
            for p, name, amount, n in top
        ],
        last_run=LastRun.model_validate(run, from_attributes=True) if run else None,
    )
