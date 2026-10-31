"""Discrepancy rules between a claim's records and its supporting documents. Pure functions over plain views.

Invoice header: invoice number, provider, patient, dates and total (informational, no amount of their own).
Matched lines: quantity, unit price, amount and service date. When both sides bill a quantity of 1, a price
difference is an amount mismatch; otherwise a quantity difference is valued at the claimed price and a price
difference at the document's quantity, so the two add up to the line's difference. Unmatched claim lines are
unsupported charges; unmatched document lines are informational.
Discharge summary: room and ICU days billed beyond the documented stay.
Amounts are calculated when the document's value was verified in its text, estimated when it was read by vision.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz, utils

from app.core.money import inr
from app.duplicates.normalise import normalise_reference

NAME_MATCH = 85
PROCEDURE_MATCH = 85
STAY_CATEGORIES = {"room", "icu"}


@dataclass(frozen=True)
class ClaimLineView:
    line_id: str
    invoice_reference: str
    service_code: str
    description: str
    category: str
    service_date: date
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class DocLineView:
    line_no: int
    service_code: str | None
    description: str | None
    service_date: date | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    page: int | None
    bbox: dict[str, float] | None
    provenance: str  # verified, page_only or unverified
    quote: str | None


@dataclass(frozen=True)
class FieldView:
    value: str | None
    page: int | None
    bbox: dict[str, float] | None
    provenance: str
    quote: str | None

    @property
    def usable(self) -> bool:
        return self.value is not None and self.provenance in ("verified", "page_only")


@dataclass
class Finding:
    type: str
    explanation: str
    claim_value: str | None = None
    document_value: str | None = None
    difference: Decimal | None = None
    amount_impact: Decimal | None = None
    amount_type: str | None = None
    claim_line: ClaimLineView | None = None
    doc_line: DocLineView | None = None
    page: int | None = None
    bbox: dict[str, float] | None = None
    quote: str | None = None
    generated_by: str = "rule"
    extra: dict[str, Any] = field(default_factory=dict)


def qty(value: Decimal) -> str:
    """A quantity as written: 5, 2.5 (never 5.00)."""
    return f"{value.normalize():f}"


def _amount_type(provenance: str) -> str:
    return "calculated" if provenance == "verified" else "estimated"


def _from_doc_line(doc: DocLineView) -> dict[str, Any]:
    return {"page": doc.page, "bbox": doc.bbox, "quote": doc.quote}


def line_findings(claim: ClaimLineView, doc: DocLineView) -> list[Finding]:
    """Differences between a claim line and the document line it was matched to."""
    findings: list[Finding] = []
    money = doc.provenance in ("verified", "page_only")
    kind = _amount_type(doc.provenance)
    cq, cp, ca = claim.quantity, claim.unit_price, claim.amount
    dq, dp, da = doc.quantity, doc.unit_price, doc.amount
    label = f'"{claim.description}" ({claim.line_id})'
    if money and dq is not None and dp is not None:
        if cq != dq:
            impact = (cq - dq) * cp
            findings.append(
                Finding(
                    "QUANTITY_MISMATCH",
                    f"{label}: claimed quantity {qty(cq)}, the document shows {qty(dq)}; "
                    f"({qty(cq)} - {qty(dq)}) × {inr(cp)} = {inr(impact)}.",
                    f"{qty(cq)}",
                    f"{qty(dq)}",
                    cq - dq,
                    impact if impact > 0 else None,
                    kind if impact > 0 else None,
                    claim,
                    doc,
                    **_from_doc_line(doc),
                )
            )
        if cp != dp:
            if cq == dq == 1:
                impact = ca - (da if da is not None else dp)
                findings.append(
                    Finding(
                        "AMOUNT_MISMATCH",
                        f"{label}: claimed {inr(ca)}, the document shows {inr(ca - impact)}; "
                        f"{inr(ca)} - {inr(ca - impact)} = {inr(impact)}.",
                        str(ca),
                        str(ca - impact),
                        impact,
                        impact if impact > 0 else None,
                        kind if impact > 0 else None,
                        claim,
                        doc,
                        **_from_doc_line(doc),
                    )
                )
            else:
                impact = (cp - dp) * dq
                findings.append(
                    Finding(
                        "UNIT_PRICE_MISMATCH",
                        f"{label}: claimed unit price {inr(cp)}, the document shows "
                        f"{inr(dp)}; ({inr(cp)} - {inr(dp)}) × {qty(dq)} = {inr(impact)}.",
                        str(cp),
                        str(dp),
                        cp - dp,
                        impact if impact > 0 else None,
                        kind if impact > 0 else None,
                        claim,
                        doc,
                        **_from_doc_line(doc),
                    )
                )
        elif cq == dq and da is not None and ca != da:
            impact = ca - da
            findings.append(
                Finding(
                    "AMOUNT_MISMATCH",
                    f"{label}: claimed {inr(ca)}, the document shows {inr(da)}.",
                    str(ca),
                    str(da),
                    impact,
                    impact if impact > 0 else None,
                    kind if impact > 0 else None,
                    claim,
                    doc,
                    **_from_doc_line(doc),
                )
            )
    if doc.service_date is not None and doc.service_date != claim.service_date:
        findings.append(
            Finding(
                "SERVICE_DATE_MISMATCH",
                f"{label}: claimed on {claim.service_date:%d %b %Y}, the document shows {doc.service_date:%d %b %Y}.",
                claim.service_date.isoformat(),
                doc.service_date.isoformat(),
                None,
                None,
                None,
                claim,
                doc,
                **_from_doc_line(doc),
            )
        )
    return findings


def unmatched_claim_finding(claim: ClaimLineView, invoice_number: str | None) -> Finding:
    on = f"invoice {invoice_number}" if invoice_number else "the invoice"
    return Finding(
        "ONLY_IN_CLAIM",
        f'"{claim.description}" ({claim.line_id}) {inr(claim.amount)} is not on {on}: an unsupported charge.',
        str(claim.amount),
        None,
        claim.amount,
        claim.amount,
        "calculated",
        claim,
        None,
    )


def unmatched_document_finding(doc: DocLineView) -> Finding:
    amount = inr(doc.amount) if doc.amount is not None else "an amount"
    return Finding(
        "ONLY_IN_DOCUMENT",
        f'"{doc.description}" ({amount}) is on the document but not claimed (usually benign).',
        None,
        str(doc.amount) if doc.amount is not None else None,
        None,
        None,
        None,
        None,
        doc,
        **_from_doc_line(doc),
    )


@dataclass(frozen=True)
class ClaimHeader:
    claim_id: str
    claimant_name: str
    incident_date: date
    provider_names: tuple[str, ...]


def _field_ref(f: FieldView) -> dict[str, Any]:
    return {"page": f.page, "bbox": f.bbox, "quote": f.quote}


def header_findings(claim: ClaimHeader, lines: list[ClaimLineView], header: dict[str, FieldView]) -> list[Finding]:
    """Invoice header against the claim: number, provider, patient, dates and total."""
    findings: list[Finding] = []
    number = header.get("invoice_number")
    if number is not None and number.usable:
        refs = {normalise_reference(ln.invoice_reference) for ln in lines}
        if normalise_reference(number.value) not in refs:
            claimed = ", ".join(sorted({ln.invoice_reference for ln in lines}))
            findings.append(
                Finding(
                    "INVOICE_REF_MISMATCH",
                    f"The document's invoice number {number.value} is not one the claim lists ({claimed}).",
                    claimed,
                    number.value,
                    **_field_ref(number),
                )
            )
    provider = header.get("provider_name")
    if provider is not None and provider.usable and claim.provider_names:
        best = max(
            fuzz.token_set_ratio(provider.value, p, processor=utils.default_process) for p in claim.provider_names
        )
        if best < NAME_MATCH:
            findings.append(
                Finding(
                    "PROVIDER_MISMATCH",
                    f"The document is from {provider.value}; the claim lines are "
                    f"from {', '.join(claim.provider_names)}.",
                    ", ".join(claim.provider_names),
                    provider.value,
                    **_field_ref(provider),
                )
            )
    patient = header.get("patient_name")
    if patient is not None and patient.usable:
        score = fuzz.token_set_ratio(patient.value, claim.claimant_name, processor=utils.default_process)
        if score < NAME_MATCH:
            findings.append(
                Finding(
                    "PATIENT_MISMATCH",
                    f"The document is for {patient.value}; the claimant is {claim.claimant_name}.",
                    claim.claimant_name,
                    patient.value,
                    **_field_ref(patient),
                )
            )
    admission = header.get("admission_date")
    if admission is not None and admission.usable and date.fromisoformat(admission.value) != claim.incident_date:
        findings.append(
            Finding(
                "DATE_MISMATCH",
                f"The document's admission or visit date {admission.value} differs "
                f"from the claim's incident date {claim.incident_date.isoformat()}.",
                claim.incident_date.isoformat(),
                admission.value,
                **_field_ref(admission),
            )
        )
    invoice_date = header.get("invoice_date")
    if invoice_date is not None and invoice_date.usable and lines:
        last = max(ln.service_date for ln in lines)
        if date.fromisoformat(invoice_date.value) < last:
            findings.append(
                Finding(
                    "DATE_MISMATCH",
                    f"The invoice is dated {invoice_date.value}, before the last "
                    f"claimed service on {last.isoformat()}.",
                    last.isoformat(),
                    invoice_date.value,
                    **_field_ref(invoice_date),
                )
            )
    total = header.get("total")
    if total is not None and total.usable and lines:
        claimed = sum((ln.amount for ln in lines), Decimal(0))
        printed = Decimal(total.value)
        if claimed != printed:
            findings.append(
                Finding(
                    "TOTAL_MISMATCH",
                    f"The claim lines for this invoice total {inr(claimed)}; the document's total is {inr(printed)}.",
                    str(claimed),
                    str(printed),
                    claimed - printed,
                    **_field_ref(total),
                )
            )
    return findings


def stay_findings(
    lines: list[ClaimLineView], admission: date, discharge: date, ref: dict[str, Any] | None = None
) -> list[Finding]:
    """Room and ICU days billed beyond discharge - admission, valued at the room rate."""
    stay_lines = sorted((ln for ln in lines if ln.category in STAY_CATEGORIES), key=lambda ln: ln.line_id)
    if not stay_lines:
        return []
    billed = sum((ln.quantity for ln in stay_lines), Decimal(0))
    stay = Decimal((discharge - admission).days)
    if billed <= stay:
        return []
    rooms = [ln for ln in stay_lines if ln.category == "room"] or stay_lines
    rate = min(ln.unit_price for ln in rooms)
    extra = billed - stay
    impact = extra * rate
    first = rooms[0]
    return [
        Finding(
            "STAY_LENGTH_MISMATCH",
            f"Billed {qty(billed)} room and ICU days; the discharge summary shows {qty(stay)} "
            f"({admission:%d %b} to {discharge:%d %b %Y}): {qty(extra)} × {inr(rate)} = {inr(impact)}.",
            f"{qty(billed)} days",
            f"{qty(stay)} days",
            extra,
            impact,
            "calculated",
            first,
            None,
            **(ref or {}),
        )
    ]


def documented_by_rule(procedure: str, performed: list[str]) -> str | None:
    """The summary entry that names the billed procedure, if any (no model needed)."""
    for text in performed:
        if fuzz.token_set_ratio(procedure, text, processor=utils.default_process) >= PROCEDURE_MATCH:
            return text
    return None
