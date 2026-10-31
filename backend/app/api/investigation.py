"""The integration contract for the investigation workspace, decisions and audit trail: one bundle per claim, the
evidence export with every version and event, and the claim's machine-generated history.

Everything here is read-only and built from the same functions as the individual endpoints, so the bundle and the
endpoints cannot disagree. Analysis results are append-only: a decision references (finding_id, finding_version).
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import any_, literal, select

from app.api.claim_documents import (
    ClaimDocumentOut,
    DiscrepancyOut,
    DocumentComparisonOut,
    ExtractionOut,
    document_comparison,
    extraction_out,
    list_claim_documents,
)
from app.api.claims import (
    AlertBrief,
    ClaimOut,
    LineOut,
    MatchOut,
    PolicyOut,
    ResultOut,
    SettlementOut,
    StepOut,
    claim_detail,
)
from app.api.corrections import CorrectionSetOut, set_out
from app.api.graph import GroupOut, RelatedOut, related
from app.core.security import get_current_user
from app.corrections.service import latest_set
from app.db.models import (
    AnalysisEvent,
    CorrectionSet,
    Document,
    DocumentComparison,
    DocumentDiscrepancy,
    DocumentExtraction,
    RelationshipGroup,
)
from app.db.session import SessionDep
from app.documents.claim_documents import latest_extraction

router = APIRouter(tags=["investigation"], dependencies=[Depends(get_current_user)])
POLICY_APPLICATION = {"APPLY_DEDUCTIBLE", "APPLY_COPAY", "RECOVER_OVERPAYMENT"}


class DocumentBundle(ClaimDocumentOut):
    latest_extraction: ExtractionOut | None = None


class LeakageSummary(BaseModel):
    """requested - corrections = recommended payable. Calculated leakage is what the applied corrections take off
    beyond normal policy application (deductible and co-pay); estimated is the items for review; recovery is what a
    settled claim was overpaid."""

    requested: Decimal
    recommended_payable: Decimal | None
    calculated: Decimal
    estimated: Decimal
    recovery: Decimal


class FindingRef(BaseModel):
    finding_id: str
    finding_version: int
    kind: str  # alert, discrepancy, relationship_group or correction


class InvestigationBundle(BaseModel):
    claim: ClaimOut
    lines: list[LineOut]
    policy: PolicyOut
    settlement: SettlementOut | None
    validation_results: list[ResultOut]
    payable_steps: list[StepOut]
    duplicates: list[MatchOut]
    alerts: list[AlertBrief]
    related: RelatedOut
    documents: list[DocumentBundle]
    document_comparison: DocumentComparisonOut
    corrections: CorrectionSetOut | None
    leakage: LeakageSummary
    finding_ids: list[FindingRef]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    event_type: str
    claim_id: str | None
    entity_type: str
    entity_id: str
    actor_type: str
    model: str | None
    prompt_version: str | None
    payload: dict[str, Any] | None
    created_at: datetime


class ComparisonVersion(BaseModel):
    comparison_id: int
    document_id: int
    extraction_id: int
    version: int
    created_at: datetime
    line_matches: dict[str, Any]
    discrepancies: list[DiscrepancyOut]


class EvidenceExport(BaseModel):
    exported_at: datetime
    bundle: InvestigationBundle
    extractions: list[ExtractionOut]
    document_comparisons: list[ComparisonVersion]
    correction_sets: list[CorrectionSetOut]
    relationship_groups: list[GroupOut]
    events: list[EventOut]


def _leakage(bundle_claim: ClaimOut, corrections: CorrectionSetOut | None, alerts: list[AlertBrief]) -> LeakageSummary:
    if corrections is None:
        calculated = sum((a.amount or Decimal(0) for a in alerts if a.amount_type == "calculated"), Decimal(0))
        estimated = sum((a.amount or Decimal(0) for a in alerts if a.amount_type == "estimated"), Decimal(0))
        return LeakageSummary(
            requested=bundle_claim.requested_amount,
            recommended_payable=bundle_claim.payable,
            calculated=calculated,
            estimated=estimated,
            recovery=Decimal(0),
        )
    applied = [c for c in corrections.corrections if c.applied and c.type not in POLICY_APPLICATION]
    review = [c for c in corrections.corrections if not c.applied]
    return LeakageSummary(
        requested=corrections.requested_amount,
        recommended_payable=corrections.recommended_payable,
        calculated=sum((c.difference for c in applied), Decimal(0)),
        estimated=sum((c.difference for c in review), Decimal(0)),
        recovery=corrections.recovery_amount or Decimal(0),
    )


async def build_bundle(claim_id: str, session: SessionDep) -> InvestigationBundle:
    detail = await claim_detail(session, claim_id)
    documents = []
    for document in await list_claim_documents(claim_id, session):
        extraction = await latest_extraction(session, document.id)
        documents.append(
            DocumentBundle(
                **document.model_dump(),
                latest_extraction=await extraction_out(session, extraction) if extraction else None,
            )
        )
    comparison = await document_comparison(claim_id, session)
    correction_set = await latest_set(session, claim_id)
    corrections = await set_out(session, correction_set) if correction_set else None
    graph = await related(claim_id, session)
    findings = [
        FindingRef(
            finding_id=a.finding_id, finding_version=a.run_id or a.graph_build_id or a.comparison_id or 1, kind="alert"
        )
        for a in detail.alerts
    ]
    findings += [
        FindingRef(finding_id=d.discrepancy_id, finding_version=d.version, kind="discrepancy")
        for c in comparison.comparisons
        for d in c.discrepancies
    ]
    findings += [
        FindingRef(finding_id=g.group_id, finding_version=g.version, kind="relationship_group") for g in graph.groups
    ]
    if corrections is not None:
        findings += [
            FindingRef(finding_id=c.correction_id, finding_version=corrections.version, kind="correction")
            for c in corrections.corrections
        ]
    return InvestigationBundle(
        claim=detail.claim,
        lines=detail.lines,
        policy=detail.policy,
        settlement=detail.settlement,
        validation_results=detail.results,
        payable_steps=detail.payable_steps,
        duplicates=detail.duplicates,
        alerts=detail.alerts,
        related=graph,
        documents=documents,
        document_comparison=comparison,
        corrections=corrections,
        leakage=_leakage(detail.claim, corrections, detail.alerts),
        finding_ids=findings,
    )


@router.get("/claims/{claim_id}/investigation")
async def investigation(claim_id: str, session: SessionDep) -> InvestigationBundle:
    return await build_bundle(claim_id, session)


async def _events(session: SessionDep, claim_id: str) -> list[EventOut]:
    rows = await session.scalars(
        select(AnalysisEvent)
        .where(AnalysisEvent.claim_id == claim_id)
        .order_by(AnalysisEvent.created_at, AnalysisEvent.event_id)
    )
    return [EventOut.model_validate(e) for e in rows]


@router.get("/claims/{claim_id}/events")
async def claim_events(claim_id: str, session: SessionDep) -> list[EventOut]:
    await claim_detail(session, claim_id)  # 404 for an unknown claim
    return await _events(session, claim_id)


@router.get("/claims/{claim_id}/evidence.json", response_model=EvidenceExport)
async def evidence_export(claim_id: str, session: SessionDep) -> Response:
    """The bundle plus every version and event: the data source for the downloadable report."""
    bundle = await build_bundle(claim_id, session)
    document_ids = list(await session.scalars(select(Document.id).where(Document.claim_id == claim_id)))
    extractions = [
        await extraction_out(session, e)
        for e in await session.scalars(
            select(DocumentExtraction)
            .where(DocumentExtraction.document_id.in_(document_ids))
            .order_by(DocumentExtraction.document_id, DocumentExtraction.version)
        )
    ]
    comparisons = []
    for c in await session.scalars(
        select(DocumentComparison)
        .where(DocumentComparison.claim_id == claim_id)
        .order_by(DocumentComparison.document_id, DocumentComparison.version)
    ):
        rows = await session.scalars(
            select(DocumentDiscrepancy)
            .where(DocumentDiscrepancy.comparison_id == c.comparison_id)
            .order_by(DocumentDiscrepancy.discrepancy_id)
        )
        comparisons.append(
            ComparisonVersion(
                comparison_id=c.comparison_id,
                document_id=c.document_id,
                extraction_id=c.extraction_id,
                version=c.version,
                created_at=c.created_at,
                line_matches=c.line_matches or {},
                discrepancies=[DiscrepancyOut.model_validate(r) for r in rows],
            )
        )
    sets = [
        await set_out(session, s)
        for s in await session.scalars(
            select(CorrectionSet).where(CorrectionSet.claim_id == claim_id).order_by(CorrectionSet.version)
        )
    ]
    groups = [
        GroupOut.model_validate(g)
        for g in await session.scalars(
            select(RelationshipGroup)
            .where(literal(claim_id) == any_(RelationshipGroup.claim_ids))
            .order_by(RelationshipGroup.group_id, RelationshipGroup.version)
        )
    ]
    export = EvidenceExport(
        exported_at=datetime.now().astimezone(),
        bundle=bundle,
        extractions=extractions,
        document_comparisons=comparisons,
        correction_sets=sets,
        relationship_groups=groups,
        events=await _events(session, claim_id),
    )
    return Response(
        json.dumps(export.model_dump(mode="json"), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{claim_id}-evidence.json"'},
    )
