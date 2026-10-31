"""Investigation evidence: the history of every claim under investigation, overrides, notes and the report."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.api.pagination import Page, PageDep
from app.core.security import CurrentUser
from app.db.session import SessionDep
from app.evidence import service
from app.evidence.report import build_report, render_pdf
from app.evidence.view import investigation_view, investigations_list

router = APIRouter(prefix="/evidence", tags=["evidence"])


# Until roles land, the signed-in username is the identity and the role is unknown.
def _actor(username: str) -> tuple[str, str | None]:
    return username, None


class RecommendationOut(BaseModel):
    action: str
    basis: str
    original_amount: Decimal
    correction: Decimal | None
    corrected_amount: Decimal | None
    amount_type: str
    calculation: str | None
    rule_or_pattern: str
    policy_rule_id: str | None
    source: str


class EvidenceOverride(BaseModel):
    previous_correction: Decimal | None
    new_correction: Decimal
    reason: str
    reverted: bool
    actor: str
    at: datetime
    seq: int


class EvidenceDecision(BaseModel):
    status: str | None
    note: str | None
    actor: str
    actor_role: str | None
    at: datetime
    seq: int


class EvidenceFinding(BaseModel):
    key: str
    alert_id: int
    category: str
    category_label: str
    severity: str
    status: str
    line_id: str | None
    explanation: str
    recommendation: RecommendationOut
    original_recommendation: RecommendationOut | None
    changed_since_opened: bool
    effective_correction: Decimal | None
    effective_corrected_amount: Decimal | None
    override: EvidenceOverride | None
    decision: EvidenceDecision | None


class EvidenceEventOut(BaseModel):
    seq: int
    at: datetime
    actor: str
    actor_role: str | None
    kind: Literal["opened", "recalculated", "decision", "override", "note", "exported"]
    finding_key: str | None
    alert_id: int | None
    summary: str
    payload: dict[str, Any]
    prev_hash: str | None
    hash: str


class EvidenceIntegrity(BaseModel):
    verified: bool
    events: int
    head_hash: str | None
    broken_at: int | None
    reason: str | None


class EvidenceSummary(BaseModel):
    original_calculated_leakage: Decimal | None
    current_calculated_leakage: Decimal
    adjusted_calculated_leakage: Decimal
    estimated_leakage: Decimal
    findings: int
    overrides: int
    decided: int
    counts: dict[str, int]


class EvidenceClaim(BaseModel):
    claim_id: str
    claimant_name: str
    policy_number: str
    claim_type: str
    status: str
    incident_date: date
    requested_amount: Decimal


class InvestigationBrief(BaseModel):
    opened_at: datetime
    opened_by: str
    events: int
    head_hash: str | None


class EvidenceOriginal(BaseModel):
    run_id: int | None
    totals: dict[str, Any] | None
    payable_steps: list[dict[str, Any]]
    results: list[dict[str, Any]]


class InvestigationOut(BaseModel):
    claim: EvidenceClaim
    investigation: InvestigationBrief | None
    integrity: EvidenceIntegrity
    summary: EvidenceSummary
    findings: list[EvidenceFinding]
    original: EvidenceOriginal | None
    events: list[EvidenceEventOut]


class InvestigationRow(BaseModel):
    claim_id: str
    claimant_name: str
    claim_type: str
    opened_at: datetime
    opened_by: str
    events: int
    head_hash: str | None
    last_event_at: datetime | None
    last_event_kind: str | None
    last_event_summary: str | None
    last_actor: str | None


class EvidenceOverrideIn(BaseModel):
    alert_id: int
    correction: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Give a reason of at least 5 characters for changing the recommendation")
        return value


class EvidenceNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    alert_id: int | None = None

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A note cannot be empty")
        return value


@router.get("")
async def list_investigations(session: SessionDep, page: PageDep) -> Page[InvestigationRow]:
    items, total = await investigations_list(session, page.offset, page.page_size)
    return Page(items=[InvestigationRow.model_validate(i) for i in items], total=total)


@router.get("/claims/{claim_id}")
async def get_investigation(claim_id: str, session: SessionDep) -> InvestigationOut:
    return InvestigationOut.model_validate(await investigation_view(session, claim_id))


@router.post("/claims/{claim_id}/open")
async def open_investigation(claim_id: str, session: SessionDep, username: CurrentUser) -> InvestigationOut:
    actor, role = _actor(username)
    await service.open_investigation(session, claim_id, actor, role)
    await session.commit()
    return InvestigationOut.model_validate(await investigation_view(session, claim_id))


@router.post("/claims/{claim_id}/overrides", status_code=201)
async def override(
    claim_id: str, body: EvidenceOverrideIn, session: SessionDep, username: CurrentUser
) -> InvestigationOut:
    actor, role = _actor(username)
    await service.override_correction(session, claim_id, body.alert_id, body.correction, body.reason, actor, role)
    await session.commit()
    return InvestigationOut.model_validate(await investigation_view(session, claim_id))


@router.post("/claims/{claim_id}/notes", status_code=201)
async def add_note(claim_id: str, body: EvidenceNoteIn, session: SessionDep, username: CurrentUser) -> InvestigationOut:
    actor, role = _actor(username)
    await service.add_note(session, claim_id, body.text, actor, role, body.alert_id)
    await session.commit()
    return InvestigationOut.model_validate(await investigation_view(session, claim_id))


@router.get("/claims/{claim_id}/report")
async def download_report(
    claim_id: str, session: SessionDep, username: CurrentUser, format: Literal["pdf", "json"] = "pdf"
) -> Response:
    """Downloading is itself recorded, so the report covers its own export entry."""
    actor, role = _actor(username)
    await service.record_export(session, claim_id, format, actor, role)
    await session.commit()
    report = build_report(await investigation_view(session, claim_id, full=True), actor)
    filename = f"investigation-{claim_id}"
    if format == "json":
        body = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
        return Response(
            body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )
    return Response(
        render_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )
