"""One read model for an investigation, used by the API and by the downloadable report."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AmountType, EvidenceKind
from app.db.models import Alert, AnalysisEvent, Claim, EvidenceEvent, Investigation
from app.evidence import service
from app.evidence.chain import Verification, verify
from app.evidence.recommend import finding_key, recommendation

# Parts of a snapshot too large for the timeline; the full copy stays in the stored entry and the JSON report.
HEAVY = ("claim", "policy", "lines", "settlement", "results", "duplicates")


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def light_payload(event: EvidenceEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    if event.kind == EvidenceKind.OPENED.value:
        return {k: v for k, v in payload.items() if k not in HEAVY}
    if event.kind == EvidenceKind.RECALCULATED.value:
        snap = payload.get("snapshot", {})
        return {**payload, "snapshot": {k: v for k, v in snap.items() if k not in HEAVY}}
    return payload


def event_dict(event: EvidenceEvent, full: bool = False) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "at": event.at,
        "actor": event.actor,
        "actor_role": event.actor_role,
        "kind": event.kind,
        "finding_key": event.finding_key,
        "alert_id": event.alert_id,
        "summary": event.summary,
        "payload": event.payload if full else light_payload(event),
        "prev_hash": event.prev_hash,
        "hash": event.hash,
    }


def _latest_decisions(events: list[EvidenceEvent]) -> dict[str, EvidenceEvent]:
    latest: dict[str, EvidenceEvent] = {}
    for event in events:
        if event.kind == EvidenceKind.DECISION.value and event.finding_key:
            latest[event.finding_key] = event
    return latest


async def investigation_view(session: AsyncSession, claim_id: str, full: bool = False) -> dict[str, Any]:
    claim, lines, settlement = await service._context(session, claim_id)
    investigation = await session.get(Investigation, claim_id)
    events = await service.events_for(session, claim_id) if investigation else []
    check = verify(events, investigation.head_hash) if investigation else Verification(True, 0, None)
    originals = service.original_findings(events)
    overrides = service.latest_overrides(events)
    decisions = _latest_decisions(events)
    opened = next((e for e in events if e.kind == EvidenceKind.OPENED.value), None)

    alerts = list(await session.scalars(select(Alert).where(Alert.claim_id == claim_id).order_by(Alert.id)))
    # System and AI analysis steps (graph builds, extractions, comparisons, corrections) recorded by the
    # analysis pipeline; shown beside the analysts' entries, outside the hash chain.
    analysis = list(
        await session.scalars(
            select(AnalysisEvent).where(AnalysisEvent.claim_id == claim_id).order_by(AnalysisEvent.created_at.desc())
        )
    )
    findings = []
    for alert in alerts:
        key = finding_key(alert)
        current = recommendation(alert, claim, lines, settlement)
        original = (originals.get(key) or {}).get("recommendation")
        override = overrides.get(key)
        decision = decisions.get(key)
        effective = _dec(override["new_correction"]) if override else current["correction"]
        findings.append(
            {
                "key": key,
                "alert_id": alert.id,
                "category": alert.category,
                "category_label": service.category_label(alert.category),
                "severity": alert.severity,
                "status": alert.status,
                "line_id": alert.line_id,
                "explanation": alert.explanation,
                "recommendation": current,
                "original_recommendation": original,
                "changed_since_opened": original is not None and _dec(original["correction"]) != current["correction"],
                "effective_correction": effective,
                "effective_corrected_amount": (
                    None if effective is None else max(Decimal("0"), current["original_amount"] - effective)
                ),
                "override": (
                    {
                        "previous_correction": override["previous_correction"],
                        "new_correction": override["new_correction"],
                        "reason": override["reason"],
                        "reverted": override["reverted"],
                        "actor": override["actor"],
                        "at": override["at"],
                        "seq": override["seq"],
                    }
                    if override
                    else None
                ),
                "decision": (
                    {
                        "status": decision.payload.get("status"),
                        "note": decision.payload.get("note"),
                        "actor": decision.actor,
                        "actor_role": decision.actor_role,
                        "at": decision.at,
                        "seq": decision.seq,
                    }
                    if decision
                    else None
                ),
            }
        )

    def total(values: list[tuple[str, Any]]) -> Decimal:
        return sum(
            (Decimal(str(v)) for t, v in values if t == AmountType.CALCULATED.value and v is not None), Decimal("0")
        )

    counts = {kind.value: 0 for kind in EvidenceKind}
    for event in events:
        counts[event.kind] += 1
    summary = {
        "original_calculated_leakage": (_dec(opened.payload["totals"]["calculated_leakage"]) if opened else None),
        "current_calculated_leakage": total(
            [(f["recommendation"]["amount_type"], f["recommendation"]["correction"]) for f in findings]
        ),
        "adjusted_calculated_leakage": total(
            [(f["recommendation"]["amount_type"], f["effective_correction"]) for f in findings]
        ),
        "estimated_leakage": sum(
            (
                f["recommendation"]["correction"] or Decimal("0")
                for f in findings
                if f["recommendation"]["amount_type"] == AmountType.ESTIMATED.value
            ),
            Decimal("0"),
        ),
        "findings": len(findings),
        "overrides": sum(1 for f in findings if f["override"] and not f["override"]["reverted"]),
        "decided": sum(1 for f in findings if f["decision"]),
        "counts": counts,
    }
    return {
        "claim": {
            "claim_id": claim.claim_id,
            "claimant_name": claim.claimant_name,
            "policy_number": claim.policy_number,
            "claim_type": claim.claim_type,
            "status": claim.status,
            "incident_date": claim.incident_date,
            "requested_amount": claim.requested_amount,
        },
        "investigation": (
            {
                "opened_at": investigation.opened_at,
                "opened_by": investigation.opened_by,
                "events": investigation.event_count,
                "head_hash": investigation.head_hash,
            }
            if investigation
            else None
        ),
        "integrity": {
            "verified": check.verified,
            "events": check.events,
            "head_hash": check.head_hash,
            "broken_at": check.broken_at,
            "reason": check.reason,
        },
        "summary": summary,
        "findings": findings,
        "original": (
            {
                "run_id": opened.payload.get("run_id"),
                "totals": opened.payload.get("totals"),
                "payable_steps": opened.payload.get("payable_steps", []),
                "results": [r for r in opened.payload.get("results", []) if r.get("outcome") in ("fail", "adjusted")],
            }
            if opened
            else None
        ),
        "events": [event_dict(e, full) for e in reversed(events)],
        "analysis_events": [
            {
                "event_id": a.event_id,
                "event_type": a.event_type,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "actor_type": a.actor_type,
                "model": a.model,
                "prompt_version": a.prompt_version,
                "payload": a.payload if full else None,
                "created_at": a.created_at,
            }
            for a in analysis
        ],
    }


async def investigations_list(session: AsyncSession, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    total = await session.scalar(select(func.count()).select_from(Investigation))
    rows = (
        await session.execute(
            select(Investigation, Claim)
            .join(Claim, Claim.claim_id == Investigation.claim_id)
            .order_by(Investigation.opened_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for investigation, claim in rows:
        last = await session.scalar(
            select(EvidenceEvent)
            .where(EvidenceEvent.claim_id == claim.claim_id)
            .order_by(EvidenceEvent.seq.desc())
            .limit(1)
        )
        items.append(
            {
                "claim_id": claim.claim_id,
                "claimant_name": claim.claimant_name,
                "claim_type": claim.claim_type,
                "opened_at": investigation.opened_at,
                "opened_by": investigation.opened_by,
                "events": investigation.event_count,
                "head_hash": investigation.head_hash,
                "last_event_at": last.at if last else None,
                "last_event_kind": last.kind if last else None,
                "last_event_summary": last.summary if last else None,
                "last_actor": last.actor if last else None,
            }
        )
    return items, total or 0
