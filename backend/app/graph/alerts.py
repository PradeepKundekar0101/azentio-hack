"""Cross-claim alerts, raised on the later claim (by submission date) of each cross-policy connection in a group.

| Category                   | Amount type | Amount                                                   |
| CROSS_POLICY_INVOICE_REUSE | calculated  | the later claim's amount for the shared invoice lines    |
| INCIDENT_CLAIMED_TWICE     | estimated   | the smaller of the two claimed amounts                   |
| CONCURRENT_STAYS           | suspected   | none                                                     |
| DOCUMENT_REUSED            | calculated  | the later claim's amount supported by the reused document |
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.alerts.finding import alert_finding_id
from app.alerts.severity import severity
from app.core.config import Settings
from app.core.enums import AlertCategory, AlertStatus, AmountType, GroupTag
from app.core.money import inr
from app.graph.edges import ClaimInfo, GraphInputs, Link
from app.graph.groups import Group

RULES = {
    "shared_invoice": (AlertCategory.CROSS_POLICY_INVOICE_REUSE, AmountType.CALCULATED),
    "shared_incident": (AlertCategory.INCIDENT_CLAIMED_TWICE, AmountType.ESTIMATED),
    "overlapping_stays": (AlertCategory.CONCURRENT_STAYS, AmountType.SUSPECTED),
    "shared_document": (AlertCategory.DOCUMENT_REUSED, AmountType.CALCULATED),
}
CROSS_TAGS = {
    GroupTag.INVOICE_REUSED_ACROSS_POLICIES.value,
    GroupTag.INCIDENT_CLAIMED_TWICE.value,
    GroupTag.CONCURRENT_STAYS.value,
    GroupTag.DOCUMENT_REUSED.value,
}
CROSS_CATEGORIES = {category.value for category, _ in RULES.values()}


def _later(claims: dict[str, ClaimInfo], link: Link) -> tuple[ClaimInfo, ClaimInfo]:
    a, b = claims[link.a], claims[link.b]
    return (b, a) if (a.submission_date, a.claim_id) <= (b.submission_date, b.claim_id) else (a, b)


def _amount(
    link: Link, later: ClaimInfo, earlier: ClaimInfo, line_totals: dict[str, Decimal]
) -> tuple[Decimal | None, str | None, list[str]]:
    values = link.evidence["values"]
    if link.link_type == "shared_invoice":
        line_ids = link.evidence["source_records"]["line_ids"][later.claim_id]
        amount = sum((Decimal(v) for v in values["line_amounts"][later.claim_id]), Decimal(0))
        ref = values["invoice_reference"][later.claim_id]
        return amount, f"Lines on invoice {ref} in {later.claim_id}: {inr(amount)}", line_ids
    if link.link_type == "shared_incident":
        amount = min(later.requested_amount, earlier.requested_amount)
        calc = (
            f"Smaller of {inr(earlier.requested_amount)} ({earlier.claim_id}) and "
            f"{inr(later.requested_amount)} ({later.claim_id}): {inr(amount)} (estimate, for review)"
        )
        return amount, calc, []
    if link.link_type == "shared_document":
        amount = line_totals.get(later.claim_id, later.requested_amount)
        return amount, f"Amount of {later.claim_id} supported by the reused document: {inr(amount)}", []
    return None, None, []


def _explanation(link: Link, later: ClaimInfo, earlier: ClaimInfo) -> str:
    values = link.evidence["values"]
    if link.link_type == "shared_invoice":
        return (
            f"Invoice {values['invoice_reference'][later.claim_id]} from {values['provider_name']} "
            f"({values['provider_id']}) was already claimed in {earlier.claim_id} under {earlier.policy_number}; "
            f"{later.claim_id} claims it again under {later.policy_number}."
        )
    if link.link_type == "shared_incident":
        return (
            f"Incident {values['incident_reference'][later.claim_id]} is claimed under {earlier.policy_number} "
            f"({earlier.claim_id}) and {later.policy_number} ({later.claim_id}): possible double insurance."
        )
    if link.link_type == "overlapping_stays":
        periods = values["periods"]
        return (
            f"{later.claim_id} ({periods[later.claim_id][0]} to {periods[later.claim_id][1]}) overlaps "
            f"{earlier.claim_id} ({periods[earlier.claim_id][0]} to {periods[earlier.claim_id][1]}) for the same "
            "claimant at another hospital."
        )
    files = values["file_names"]
    return (
        f"{later.claim_id} attaches {files[later.claim_id]}, the same bill as {files[earlier.claim_id]} "
        f"on {earlier.claim_id} (hash distance {values['hash_distance']})."
    )


def cross_claim_alerts(
    build_id: int, groups: list[Group], data: GraphInputs, settings: Settings
) -> list[dict[str, Any]]:
    claims = {c.claim_id: c for c in data.claims}
    line_totals: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for ln in data.lines:
        line_totals[ln.claim_id] += ln.line_amount
    alerts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for group in groups:
        for link in group.links:
            if link.link_type not in RULES or link.tag not in CROSS_TAGS:
                continue
            category, amount_type = RULES[link.link_type]
            later, earlier = _later(claims, link)
            key = (later.claim_id, category.value, earlier.claim_id)
            if key in alerts:
                continue
            amount, calculation, line_ids = _amount(link, later, earlier, line_totals)
            edges = [
                {"a": x.a, "b": x.b, "link_type": x.link_type, "strength": x.strength, "evidence": x.evidence}
                for x in group.links
                if later.claim_id in x.pair
            ]
            alerts[key] = {
                "finding_id": alert_finding_id(
                    later.claim_id, category.value, None, link.link_type, None, earlier.claim_id
                ),
                "run_id": None,
                "graph_build_id": build_id,
                "claim_id": later.claim_id,
                "line_id": None,
                "category": category.value,
                "severity": severity(category, amount_type, amount, settings).value,
                "amount": amount,
                "amount_type": amount_type.value,
                "calculation": calculation,
                "rule_or_pattern": link.link_type.upper(),
                "policy_rule_id": None,
                "explanation": _explanation(link, later, earlier),
                "supporting": {
                    "claim_id": later.claim_id,
                    "policy_number": later.policy_number,
                    "group_id": group.group_id,
                    "matched_claim_id": earlier.claim_id,
                    "matched_claim_ids": [earlier.claim_id],
                    "line_ids": line_ids,
                    "edges": edges,
                },
                "status": AlertStatus.OPEN.value,
            }
    return [alerts[k] for k in sorted(alerts)]
