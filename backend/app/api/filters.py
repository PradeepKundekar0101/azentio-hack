"""Alert filters shared by /alerts and /dashboard/summary, so both always count the same alerts."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, exists, select

from app.core.enums import AlertCategory, AlertStatus, AmountType, ClaimType, Severity
from app.db.models import Alert, Claim, LineItem


class AlertFilters(BaseModel):
    claim_type: list[ClaimType] = []
    provider_id: list[str] = []
    category: list[AlertCategory] = []
    severity: list[Severity] = []
    amount_type: list[AmountType] = []
    status: list[AlertStatus] = []
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    date_from: date | None = None
    date_to: date | None = None

    def claim_conditions(self) -> list[Any]:
        """Conditions on the claim (and its lines): claim type, provider, incident date."""
        conditions: list[Any] = []
        if self.claim_type:
            conditions.append(Claim.claim_type.in_([c.value for c in self.claim_type]))
        if self.date_from:
            conditions.append(Claim.incident_date >= self.date_from)
        if self.date_to:
            conditions.append(Claim.incident_date <= self.date_to)
        if self.provider_id:
            conditions.append(
                exists().where(and_(LineItem.claim_id == Claim.claim_id, LineItem.provider_id.in_(self.provider_id)))
            )
        return conditions

    def alert_conditions(self) -> list[Any]:
        conditions = self.claim_conditions()
        if self.category:
            conditions.append(Alert.category.in_([c.value for c in self.category]))
        if self.severity:
            conditions.append(Alert.severity.in_([s.value for s in self.severity]))
        if self.amount_type:
            conditions.append(Alert.amount_type.in_([a.value for a in self.amount_type]))
        if self.status:
            conditions.append(Alert.status.in_([s.value for s in self.status]))
        if self.amount_min is not None:
            conditions.append(Alert.amount >= self.amount_min)
        if self.amount_max is not None:
            conditions.append(Alert.amount <= self.amount_max)
        return conditions

    def alerts(self) -> Any:
        """SELECT of matching alerts joined to their claims."""
        return select(Alert).join(Claim, Claim.claim_id == Alert.claim_id).where(*self.alert_conditions())


def alert_filters(
    claim_type: Annotated[list[ClaimType], Query()] = [],  # noqa: B006 - FastAPI query lists
    provider_id: Annotated[list[str], Query()] = [],  # noqa: B006
    category: Annotated[list[AlertCategory], Query()] = [],  # noqa: B006
    severity: Annotated[list[Severity], Query()] = [],  # noqa: B006
    amount_type: Annotated[list[AmountType], Query()] = [],  # noqa: B006
    status: Annotated[list[AlertStatus], Query()] = [],  # noqa: B006
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AlertFilters:
    return AlertFilters(
        claim_type=claim_type,
        provider_id=provider_id,
        category=category,
        severity=severity,
        amount_type=amount_type,
        status=status,
        amount_min=amount_min,
        amount_max=amount_max,
        date_from=date_from,
        date_to=date_to,
    )


FiltersDep = Annotated[AlertFilters, Depends(alert_filters)]
