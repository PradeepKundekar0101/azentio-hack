"""Compare a claim's documents with its records and store the result.

For each document, the latest extraction is compared with the claim lines; a new comparison version is written only
when the extraction or the claim lines changed (inputs hash), so re-running costs no model calls. Discrepancies with
an amount become DOCUMENT_DISCREPANCY alerts, replaced on every comparison of the claim.
"""

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from rapidfuzz import fuzz
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.finding import alert_finding_id
from app.alerts.severity import by_amount
from app.core.config import Settings
from app.core.enums import (
    ActorType,
    AlertCategory,
    AlertStatus,
    AmountType,
    DocType,
    EventType,
    ExtractionStatus,
    GeneratedBy,
    Severity,
)
from app.core.logging import get_logger
from app.db.models import (
    Alert,
    Claim,
    Document,
    DocumentComparison,
    DocumentDiscrepancy,
    DocumentExtraction,
    ExtractedField,
    ExtractedLine,
    LineItem,
    ServiceCode,
)
from app.documents.compare import (
    ClaimHeader,
    ClaimLineView,
    DocLineView,
    FieldView,
    Finding,
    documented_by_rule,
    header_findings,
    line_findings,
    stay_findings,
    unmatched_claim_finding,
    unmatched_document_finding,
)
from app.documents.matching import Pair, assign_lines
from app.documents.provenance import normalise
from app.documents.read import PROMPT_VERSION
from app.documents.schemas import LineMatchDecision, ProcedureCheck
from app.duplicates.normalise import normalise_reference
from app.events import event, write_events

log = get_logger(__name__)
AI_MATCH_CONFIDENCE = 0.70
CODE_MATCH = 92
QUOTE_MATCH = 90


class ComparisonReader(Protocol):
    model: str

    async def same_service(self, claim_description: str, document_description: str) -> LineMatchDecision: ...

    async def check_procedure(self, procedure: str, summary_text: str) -> ProcedureCheck: ...


def discrepancy_id(claim_id: str, document_id: int, finding: Finding) -> str:
    claim_line = finding.claim_line.line_id if finding.claim_line else ""
    doc_line = str(finding.doc_line.line_no) if finding.doc_line else ""
    key = "|".join((claim_id, str(document_id), finding.type, claim_line, doc_line))
    return f"DSC-{hashlib.sha256(key.encode()).hexdigest()[:12].upper()}"


def infer_code(description: str | None, catalog: dict[str, str]) -> str | None:
    """The service code whose catalogue description the printed one is (possibly cut short): layout without codes."""
    if not description:
        return None
    printed = normalise(description)
    for code, text in catalog.items():
        full = normalise(text)
        if len(printed) >= 8 and full.startswith(printed):
            return code
    best = max(catalog.items(), key=lambda kv: fuzz.ratio(printed, normalise(kv[1])), default=None)
    if best is not None and fuzz.ratio(printed, normalise(best[1])) >= CODE_MATCH:
        return best[0]
    return None


def _quote_in(quote: str | None, text: str | None) -> bool:
    if not quote or not text:
        return False
    q, t = normalise(quote), normalise(text)
    return q in t or fuzz.partial_ratio(q, t) >= QUOTE_MATCH


class _Loaded:
    def __init__(self) -> None:
        self.claim: Claim | None = None
        self.lines: list[LineItem] = []
        self.documents: list[tuple[Document, DocumentExtraction, list[ExtractedField], list[ExtractedLine]]] = []


async def _load(session: AsyncSession, claim_id: str) -> _Loaded:
    loaded = _Loaded()
    loaded.claim = await session.get(Claim, claim_id)
    loaded.lines = list(
        await session.scalars(select(LineItem).where(LineItem.claim_id == claim_id).order_by(LineItem.line_id))
    )
    documents = list(await session.scalars(select(Document).where(Document.claim_id == claim_id).order_by(Document.id)))
    for document in documents:
        extraction = await session.scalar(
            select(DocumentExtraction)
            .where(DocumentExtraction.document_id == document.id)
            .order_by(DocumentExtraction.version.desc())
            .limit(1)
        )
        if extraction is None or extraction.status == ExtractionStatus.FAILED.value:
            continue
        fields = list(
            await session.scalars(
                select(ExtractedField).where(ExtractedField.extraction_id == extraction.extraction_id)
            )
        )
        lines = list(
            await session.scalars(
                select(ExtractedLine)
                .where(ExtractedLine.extraction_id == extraction.extraction_id)
                .order_by(ExtractedLine.line_no)
            )
        )
        loaded.documents.append((document, extraction, fields, lines))
    return loaded


def _claim_view(line: LineItem) -> ClaimLineView:
    return ClaimLineView(
        line.line_id,
        line.invoice_reference,
        line.service_code,
        line.service_description,
        line.category,
        line.service_date,
        line.quantity,
        line.unit_price,
        line.line_amount,
    )


def _field_views(fields: list[ExtractedField]) -> dict[str, FieldView]:
    return {
        f.field_path: FieldView(f.value_normalised, f.page, f.bbox, f.provenance_status, f.source_quote) for f in fields
    }


WORST = {"unverified": 0, "page_only": 1, "verified": 2}


def _doc_lines(lines: list[ExtractedLine], views: dict[str, FieldView], catalog: dict[str, str]) -> list[DocLineView]:
    out = []
    for line in lines:
        i = line.line_no - 1
        statuses = [
            views[p].provenance
            for p in (f"lines[{i}].amount", f"lines[{i}].quantity", f"lines[{i}].unit_price")
            if p in views
        ]
        provenance = min(statuses, key=WORST.__getitem__) if statuses else "unverified"
        amount_view = views.get(f"lines[{i}].amount")
        out.append(
            DocLineView(
                line_no=line.line_no,
                service_code=line.service_code or infer_code(line.description, catalog),
                description=line.description,
                service_date=line.service_date,
                quantity=line.quantity,
                unit_price=line.unit_price,
                amount=line.amount,
                page=line.page,
                bbox=line.bbox,
                provenance=provenance,
                quote=amount_view.quote if amount_view else None,
            )
        )
    return out


def inputs_hash(extraction: DocumentExtraction, lines: list[LineItem], claim: Claim) -> str:
    parts = [str(extraction.extraction_id), claim.claimant_name, claim.incident_date.isoformat()]
    parts += [
        f"{ln.line_id}|{ln.invoice_reference}|{ln.service_code}|{ln.service_date}|{ln.quantity}|{ln.unit_price}|{ln.line_amount}"
        for ln in lines
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


async def _invoice_findings(
    reader: ComparisonReader,
    loaded: _Loaded,
    extraction: DocumentExtraction,
    fields: list[ExtractedField],
    lines: list[ExtractedLine],
    catalog: dict[str, str],
) -> tuple[list[Finding], dict[str, Any]]:
    claim = loaded.claim
    assert claim is not None
    views = _field_views(fields)
    header = {path.removeprefix("header."): view for path, view in views.items() if path.startswith("header.")}
    claim_lines = [_claim_view(ln) for ln in loaded.lines]
    number = header.get("invoice_number")
    if number is not None and number.value:
        on_invoice = [
            ln for ln in claim_lines if normalise_reference(ln.invoice_reference) == normalise_reference(number.value)
        ]
        claim_lines = on_invoice or claim_lines
    doc_lines = _doc_lines(lines, views, catalog)
    assignment = assign_lines(claim_lines, doc_lines)
    pairs: list[Pair] = list(assignment.pairs)
    unmatched_claim, unmatched_doc = list(assignment.unmatched_claim), list(assignment.unmatched_document)
    for candidate in assignment.candidates:
        decision = await reader.same_service(candidate.claim.description, candidate.doc.description or "")
        if decision.same_service and decision.confidence >= AI_MATCH_CONFIDENCE:
            pairs.append(Pair(candidate.claim, candidate.doc, candidate.score, "ai", decision.confidence))
        else:
            unmatched_claim.append(candidate.claim)
            unmatched_doc.append(candidate.doc)
    providers = tuple(sorted({ln.provider_name for ln in loaded.lines}))
    findings = header_findings(
        ClaimHeader(claim.claim_id, claim.claimant_name, claim.incident_date, providers), claim_lines, header
    )
    for pair in pairs:
        for finding in line_findings(pair.claim, pair.doc):
            if pair.generated_by == "ai":
                finding.extra["match"] = {"generated_by": "ai", "model": reader.model, "confidence": pair.confidence}
            findings.append(finding)
    complete = extraction.status == ExtractionStatus.OK.value
    anchor = number or header.get("total")
    for line in sorted(unmatched_claim, key=lambda ln: ln.line_id):
        if complete:  # a line missing from an invoice that failed validation may just be misread
            finding = unmatched_claim_finding(line, number.value if number else None)
            finding.page = anchor.page if anchor else 1
            findings.append(finding)
    findings += [unmatched_document_finding(d) for d in sorted(unmatched_doc, key=lambda d: d.line_no)]
    matches = {
        "pairs": [
            {
                "claim_line_id": p.claim.line_id,
                "document_line_no": p.doc.line_no,
                "similarity": p.score,
                "generated_by": p.generated_by,
                "model": reader.model if p.generated_by == "ai" else None,
                "confidence": p.confidence,
            }
            for p in sorted(pairs, key=lambda p: p.claim.line_id)
        ],
        "unmatched_claim": sorted(ln.line_id for ln in unmatched_claim),
        "unmatched_document": sorted(d.line_no for d in unmatched_doc),
    }
    return findings, matches


async def _summary_findings(
    reader: ComparisonReader, loaded: _Loaded, extraction: DocumentExtraction, fields: list[ExtractedField]
) -> list[Finding]:
    views = _field_views(fields)
    claim_lines = [_claim_view(ln) for ln in loaded.lines]
    findings: list[Finding] = []
    admission, discharge = views.get("header.admission_date"), views.get("header.discharge_date")
    if admission and discharge and admission.usable and discharge.usable:
        ref = {"page": discharge.page, "bbox": discharge.bbox, "quote": discharge.quote}
        stays = stay_findings(
            claim_lines, date.fromisoformat(admission.value), date.fromisoformat(discharge.value), ref
        )
        for finding in stays:
            if "page_only" in (admission.provenance, discharge.provenance):
                finding.amount_type = AmountType.ESTIMATED.value
        findings += stays
    if extraction.status != ExtractionStatus.OK.value:
        return findings
    performed = [v.value for p, v in sorted(views.items()) if p.startswith("procedures[") and v.value]
    anchor = views.get("header.diagnosis") or admission
    for line in claim_lines:
        if line.category != "procedure" or documented_by_rule(line.description, performed):
            continue
        text = extraction.source_text or "\n".join(performed)
        check = await reader.check_procedure(line.description, text)
        if check.supported and _quote_in(check.quote, text):
            continue
        findings.append(
            Finding(
                "PROCEDURE_NOT_DOCUMENTED",
                f'"{line.description}" ({line.line_id}) is billed, but the discharge summary does not say it was '
                "performed.",
                str(line.amount),
                None,
                line.amount,
                line.amount,
                AmountType.ESTIMATED.value,
                line,
                None,
                page=anchor.page if anchor else 1,
                quote=check.quote,
                generated_by=GeneratedBy.AI.value,
                extra={"model": reader.model, "supported_by_model": check.supported},
            )
        )
    return findings


def _severity(finding: Finding, settings: Settings) -> str:
    if finding.amount_impact is None:
        return Severity.LOW.value
    if finding.amount_type != AmountType.CALCULATED.value:
        return Severity.REVIEW.value
    return by_amount(finding.amount_impact, settings).value


def _row(
    claim: Claim,
    document: Document,
    comparison: DocumentComparison,
    finding: Finding,
    model: str,
    settings: Settings,
    line_rows: dict[str, LineItem],
) -> dict[str, Any]:
    ai = finding.generated_by == GeneratedBy.AI.value or "match" in finding.extra
    line = finding.claim_line
    return {
        "discrepancy_id": discrepancy_id(claim.claim_id, document.id, finding),
        "comparison_id": comparison.comparison_id,
        "version": comparison.version,
        "claim_id": claim.claim_id,
        "document_id": document.id,
        "type": finding.type,
        "severity": _severity(finding, settings),
        "claim_value": finding.claim_value,
        "document_value": finding.document_value,
        "difference": finding.difference,
        "amount_impact": finding.amount_impact,
        "amount_type": finding.amount_type,
        "claim_ref": {
            "claim_id": claim.claim_id,
            "line_id": line.line_id if line else None,
            "source_row": line_rows[line.line_id].source_row
            if line and line.line_id in line_rows
            else claim.source_row,
        },
        "document_ref": {
            "document_id": document.id,
            "file_name": document.file_name,
            "page": finding.page,
            "bbox": finding.bbox,
            "quote": finding.quote,
            "line_no": finding.doc_line.line_no if finding.doc_line else None,
            **({"match": finding.extra["match"]} if "match" in finding.extra else {}),
        },
        "generated_by": GeneratedBy.AI.value if ai else GeneratedBy.RULE.value,
        "model": model if ai else None,
        "prompt_version": PROMPT_VERSION if ai else None,
        "explanation": finding.explanation,
    }


async def _catalog(session: AsyncSession) -> dict[str, str]:
    return {code: text for code, text in await session.execute(select(ServiceCode.code, ServiceCode.description))}


async def compare_claim(
    session: AsyncSession,
    reader: ComparisonReader,
    settings: Settings,
    claim_id: str,
    run_id: int | None = None,
    catalog: dict[str, str] | None = None,
) -> list[DocumentComparison]:
    """Bring every document comparison of the claim up to date and re-raise its alerts (caller commits)."""
    loaded = await _load(session, claim_id)
    claim = loaded.claim
    if claim is None:
        return []
    catalog = catalog if catalog is not None else await _catalog(session)
    line_rows = {ln.line_id: ln for ln in loaded.lines}
    current: list[DocumentComparison] = []
    events = []
    for document, extraction, fields, lines in loaded.documents:
        digest = inputs_hash(extraction, loaded.lines, claim)
        latest = await session.scalar(
            select(DocumentComparison)
            .where(DocumentComparison.document_id == document.id)
            .order_by(DocumentComparison.version.desc())
            .limit(1)
        )
        if latest is not None and latest.inputs_hash == digest:
            current.append(latest)
            continue
        if extraction.doc_type == DocType.INVOICE.value:
            findings, matches = await _invoice_findings(reader, loaded, extraction, fields, lines, catalog)
        elif extraction.doc_type == DocType.DISCHARGE_SUMMARY.value:
            findings, matches = await _summary_findings(reader, loaded, extraction, fields), {}
        else:
            continue
        comparison = DocumentComparison(
            claim_id=claim_id,
            document_id=document.id,
            extraction_id=extraction.extraction_id,
            version=(latest.version if latest else 0) + 1,
            inputs_hash=digest,
            line_matches=matches,
        )
        session.add(comparison)
        await session.flush()
        rows = [_row(claim, document, comparison, f, reader.model, settings, line_rows) for f in findings]
        if rows:
            await session.execute(insert(DocumentDiscrepancy.__table__), rows)
        current.append(comparison)
        events.append(
            event(
                EventType.COMPARISON_CREATED,
                "document_comparison",
                comparison.comparison_id,
                claim_id=claim_id,
                actor_type=ActorType.AI if any(r["generated_by"] == "ai" for r in rows) else ActorType.SYSTEM,
                model=reader.model if any(r["generated_by"] == "ai" for r in rows) else None,
                prompt_version=PROMPT_VERSION,
                document_id=document.id,
                extraction_id=extraction.extraction_id,
                version=comparison.version,
                discrepancies=len(rows),
                amount=str(sum((r["amount_impact"] or Decimal(0)) for r in rows)),
            )
        )
    await _raise_alerts(session, settings, claim, current, run_id)
    if events:
        await write_events(session, events)
    return current


async def _raise_alerts(
    session: AsyncSession, settings: Settings, claim: Claim, comparisons: list[DocumentComparison], run_id: int | None
) -> None:
    await session.execute(
        delete(Alert).where(
            Alert.claim_id == claim.claim_id, Alert.category == AlertCategory.DOCUMENT_DISCREPANCY.value
        )
    )
    if not comparisons:
        return
    by_comparison = {c.comparison_id: c for c in comparisons}
    discrepancies = list(
        await session.scalars(
            select(DocumentDiscrepancy)
            .where(DocumentDiscrepancy.comparison_id.in_(by_comparison), DocumentDiscrepancy.amount_impact > 0)
            .order_by(DocumentDiscrepancy.discrepancy_id)
        )
    )
    alerts = []
    for d in discrepancies:
        amount_type = AmountType(d.amount_type or AmountType.ESTIMATED.value)
        line_id = d.claim_ref.get("line_id")
        alerts.append(
            {
                "finding_id": alert_finding_id(
                    claim.claim_id, AlertCategory.DOCUMENT_DISCREPANCY.value, line_id, d.type, None, d.discrepancy_id
                ),
                "run_id": run_id,
                "graph_build_id": None,
                "comparison_id": None if run_id is not None else d.comparison_id,
                "claim_id": claim.claim_id,
                "line_id": line_id,
                "category": AlertCategory.DOCUMENT_DISCREPANCY.value,
                "severity": d.severity,
                "amount": d.amount_impact,
                "amount_type": amount_type.value,
                "calculation": d.explanation,
                "rule_or_pattern": d.type,
                "policy_rule_id": None,
                "explanation": d.explanation,
                "supporting": {
                    "claim_id": claim.claim_id,
                    "policy_number": claim.policy_number,
                    "discrepancy_id": d.discrepancy_id,
                    "discrepancy_version": d.version,
                    "comparison_id": d.comparison_id,
                    "document_id": d.document_id,
                    "line_ids": [line_id] if line_id else [],
                    "document_ref": d.document_ref,
                },
                "status": AlertStatus.OPEN.value,
            }
        )
    if alerts:
        await session.execute(insert(Alert.__table__), alerts)


async def compare_claims(
    session: AsyncSession, reader: ComparisonReader, settings: Settings, claim_ids: list[str] | None, run_id: int | None
) -> int:
    """Compare every claim that has documents (within claim_ids, if given). Returns the number of claims."""
    query = select(Document.claim_id).where(Document.claim_id.is_not(None)).distinct()
    if claim_ids is not None:
        query = query.where(Document.claim_id.in_(claim_ids))
    with_documents = sorted(cid for cid in await session.scalars(query) if cid)
    catalog = await _catalog(session)
    for claim_id in with_documents:
        await compare_claim(session, reader, settings, claim_id, run_id, catalog)
    return len(with_documents)


async def latest_comparisons(
    session: AsyncSession, claim_id: str, version: int | None = None
) -> list[DocumentComparison]:
    """The latest comparison of each of the claim's documents (or each document's version N)."""
    if version is not None:
        query = select(DocumentComparison).where(
            DocumentComparison.claim_id == claim_id, DocumentComparison.version == version
        )
        return list(await session.scalars(query.order_by(DocumentComparison.document_id)))
    newest = (
        select(DocumentComparison.document_id, func.max(DocumentComparison.version).label("version"))
        .where(DocumentComparison.claim_id == claim_id)
        .group_by(DocumentComparison.document_id)
        .subquery()
    )
    rows = await session.scalars(
        select(DocumentComparison)
        .join(
            newest,
            (DocumentComparison.document_id == newest.c.document_id) & (DocumentComparison.version == newest.c.version),
        )
        .order_by(DocumentComparison.document_id)
    )
    return list(rows)
