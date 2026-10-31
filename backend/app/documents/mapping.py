"""Map an extraction to the input contract: provider by fuzzy name, service codes by printed code, then fuzzy
description match. Anything unresolved is left empty for the user to fill in on the review form."""

from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz, process

from app.documents.schemas import InvoiceExtraction

PROVIDER_MIN_SCORE = 85
DESCRIPTION_MIN_SCORE = 80


@dataclass(frozen=True)
class ProviderRef:
    provider_id: str
    name: str


@dataclass(frozen=True)
class ServiceRef:
    code: str
    description: str
    category: str


def match_provider(name: str | None, providers: list[ProviderRef]) -> tuple[ProviderRef | None, float]:
    if not name or not providers:
        return None, 0.0
    found = process.extractOne(name, {p.provider_id: p.name for p in providers}, scorer=fuzz.token_sort_ratio)
    if found is None or found[1] < PROVIDER_MIN_SCORE:
        return None, float(found[1]) if found else 0.0
    return next(p for p in providers if p.provider_id == found[2]), float(found[1])


def match_service(
    code: str | None, description: str, services: list[ServiceRef]
) -> tuple[ServiceRef | None, str, float]:
    """(service, how, confidence). `how` is printed_code, description or unresolved."""
    by_code = {s.code: s for s in services}
    if code and code.strip().upper() in by_code:
        return by_code[code.strip().upper()], "printed_code", 1.0
    found = process.extractOne(description, {s.code: s.description for s in services}, scorer=fuzz.token_set_ratio)
    if found and found[1] >= DESCRIPTION_MIN_SCORE:
        return by_code[found[2]], "description", round(found[1] / 100, 2)
    return None, "unresolved", 0.0


def draft_claim(
    extraction: InvoiceExtraction, providers: list[ProviderRef], services: list[ServiceRef]
) -> dict[str, Any]:
    """The review-form draft: contract field names, with unresolved values left None."""
    provider, provider_score = match_provider(extraction.provider_name, providers)
    lines = []
    for n, line in enumerate(extraction.line_items, start=1):
        service, how, confidence = match_service(line.code, line.description, services)
        lines.append(
            {
                "line_no": n,
                "service_date": line.service_date or extraction.incident_date or extraction.invoice_date,
                "service_code": service.code if service else None,
                "service_description": line.description,
                "category": service.category if service else None,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "line_amount": line.amount,
                "code_match": how,
                "code_confidence": confidence,
            }
        )
    return {
        "claim": {
            "policy_number": extraction.policy_number,
            "claimant_id": None,
            "claimant_name": extraction.claimant_name,
            "incident_date": extraction.incident_date or extraction.invoice_date,
            "submission_date": extraction.invoice_date,
            "claim_type": None,
            "requested_amount": extraction.total,
            "incident_reference": None,
        },
        "invoice_reference": extraction.invoice_reference,
        "provider_id": provider.provider_id if provider else None,
        "provider_name": provider.name if provider else extraction.provider_name,
        "provider_match_score": provider_score,
        "lines": lines,
    }
