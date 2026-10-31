"""Recommended settlement corrections: the latest set (or a version), all versions, and a recompute that writes a new
version only when the result changed."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.errors import not_found
from app.core.security import get_current_user
from app.corrections.service import build_for_loaded, latest_set
from app.db.models import Claim, Correction, CorrectionSet
from app.db.session import SessionDep
from app.pipeline import load_claims

router = APIRouter(tags=["corrections"], dependencies=[Depends(get_current_user)])


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CorrectionOut(Orm):
    correction_id: str
    sequence: int
    type: str
    line_id: str | None
    original_amount: Decimal
    corrected_amount: Decimal
    difference: Decimal
    calculation_text: str
    calculation: dict[str, Any]
    policy_rule_id: str | None
    evidence_refs: list[str]
    amount_type: str
    confidence: Decimal | None
    generated_by: str
    applied: bool
    explanation: str


class CorrectionSetSummary(Orm):
    set_id: int
    claim_id: str
    version: int
    requested_amount: Decimal
    recommended_payable: Decimal
    total_reduction: Decimal
    paid_amount: Decimal | None
    recovery_amount: Decimal | None
    created_at: datetime


class CorrectionSetOut(CorrectionSetSummary):
    corrections: list[CorrectionOut] = []


class RecomputeOut(CorrectionSetOut):
    created: bool


async def set_out(session: SessionDep, correction_set: CorrectionSet) -> CorrectionSetOut:
    rows = await session.scalars(
        select(Correction).where(Correction.set_id == correction_set.set_id).order_by(Correction.sequence)
    )
    out = CorrectionSetOut.model_validate(correction_set)
    out.corrections = [CorrectionOut.model_validate(c) for c in rows]
    return out


@router.get("/claims/{claim_id}/corrections")
async def get_corrections(
    claim_id: str, session: SessionDep, version: Annotated[int | None, Query(ge=1)] = None
) -> CorrectionSetOut:
    correction_set = await latest_set(session, claim_id, version)
    if correction_set is None:
        raise not_found("Correction set")
    return await set_out(session, correction_set)


@router.get("/claims/{claim_id}/corrections/versions")
async def correction_versions(claim_id: str, session: SessionDep) -> list[CorrectionSetSummary]:
    rows = await session.scalars(
        select(CorrectionSet).where(CorrectionSet.claim_id == claim_id).order_by(CorrectionSet.version)
    )
    return [CorrectionSetSummary.model_validate(r) for r in rows]


@router.post("/claims/{claim_id}/corrections/recompute")
async def recompute_corrections(claim_id: str, session: SessionDep) -> RecomputeOut:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise not_found("Claim")
    loaded = await load_claims(session, [claim.policy_number])
    results = await build_for_loaded(session, loaded, [claim_id], None, only_affected=False)
    await session.commit()
    correction_set, created = results[claim_id]
    out = await set_out(session, correction_set)
    return RecomputeOut(**out.model_dump(), created=created)
