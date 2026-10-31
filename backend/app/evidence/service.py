"""Evidence history for claim investigations.

An investigation opens the first time anyone acts on a claim (a decision, an override, a note, or an explicit
open). Opening freezes the original calculation, the detected issues and the system's recommendations, so
they stay on record after later runs rebuild the alerts. Every later change is appended, never edited.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.claims import claim_detail
from app.core.enums import AlertCategory, AmountType, EvidenceKind
from app.core.errors import AppError, not_found
from app.core.money import inr
from app.db.models import Alert, Claim, EvidenceEvent, Investigation, LineItem, Settlement, ValidationResult
from app.evidence.chain import entry_hash, to_json
from app.evidence.recommend import finding, finding_key, recommendation

CHUNK = 1000
SNAPSHOT_KINDS = (EvidenceKind.OPENED.value, EvidenceKind.RECALCULATED.value)

DECISION_LABELS = {
    "open": "Reopened",
    "reviewed": "Confirmed discrepancy",
    "dismissed": "Marked as false positive",
    "evidence_requested": "Requested additional evidence",
    "escalated": "Escalated",
}

CATEGORY_LABELS = {
    AlertCategory.NOT_COVERED: "Not covered",
    AlertCategory.OUT_OF_BENEFIT_PERIOD: "Outside benefit period",
    AlertCategory.EXCLUDED_SERVICE: "Excluded service",
    AlertCategory.SUB_LIMIT_EXCEEDED: "Sub-limit exceeded",
    AlertCategory.OVERALL_LIMIT_EXCEEDED: "Overall limit exceeded",
    AlertCategory.SETTLEMENT_OVERPAYMENT: "Settlement overpayment",
    AlertCategory.EXACT_DUPLICATE_CLAIM: "Exact duplicate claim",
    AlertCategory.DUPLICATE_LINE_ITEM: "Duplicate line item",
    AlertCategory.NEAR_DUPLICATE: "Near-duplicate",
    AlertCategory.EXCESS_FREQUENCY: "Excess frequency",
}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


# Snapshots


async def _context(session: AsyncSession, claim_id: str) -> tuple[Claim, dict[str, LineItem], Settlement | None]:
    claim = await session.get(Claim, claim_id)
    if claim is None:
        raise not_found("Claim")
    lines = {ln.line_id: ln for ln in await session.scalars(select(LineItem).where(LineItem.claim_id == claim_id))}
    settlement = await session.scalar(select(Settlement).where(Settlement.claim_id == claim_id))
    return claim, lines, settlement


def _totals(findings: list[dict[str, Any]], requested: Any, payable: Any) -> dict[str, Any]:
    def total(amount_type: str) -> Decimal:
        return sum(
            (Decimal(f["amount"]) for f in findings if f["amount_type"] == amount_type and f["amount"] is not None),
            Decimal("0"),
        )

    return {
        "requested": requested,
        "payable": payable,
        "calculated_leakage": total(AmountType.CALCULATED.value),
        "estimated_leakage": total(AmountType.ESTIMATED.value),
        "findings": len(findings),
    }


async def snapshot(session: AsyncSession, claim_id: str) -> dict[str, Any]:
    """Everything the claim's numbers rest on, as plain JSON: the claim, policy terms, lines, every check
    result, the payable steps, duplicate decisions and each finding with its recommendation."""
    detail = (await claim_detail(session, claim_id)).model_dump(mode="json")
    claim, lines, settlement = await _context(session, claim_id)
    alerts = list(await session.scalars(select(Alert).where(Alert.claim_id == claim_id).order_by(Alert.id)))
    run_id = await session.scalar(
        select(func.max(ValidationResult.run_id)).where(ValidationResult.claim_id == claim_id)
    )
    findings = to_json([finding(a, claim, lines, settlement) for a in alerts])
    return to_json(
        {
            "run_id": run_id,
            "claim": detail["claim"],
            "policy": detail["policy"],
            "lines": detail["lines"],
            "settlement": detail["settlement"],
            "results": detail["results"],
            "payable_steps": detail["payable_steps"],
            "duplicates": detail["duplicates"],
            "findings": findings,
            "totals": _totals(findings, detail["claim"]["requested_amount"], detail["claim"]["payable"]),
        }
    )


def _changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old = {f["key"]: f for f in before.get("findings", [])}
    new = {f["key"]: f for f in after.get("findings", [])}
    fields = ("amount", "amount_type", "calculation", "severity")
    changed = [
        {"key": key, "before": {k: old[key][k] for k in fields}, "after": {k: new[key][k] for k in fields}}
        for key in old.keys() & new.keys()
        if any(old[key][k] != new[key][k] for k in fields)
    ]
    payable = (before.get("totals", {}).get("payable"), after.get("totals", {}).get("payable"))
    return {
        "added": [new[k] for k in sorted(new.keys() - old.keys())],
        "removed": [old[k] for k in sorted(old.keys() - new.keys())],
        "changed": sorted(changed, key=lambda c: c["key"]),
        "payable": {"before": payable[0], "after": payable[1]} if payable[0] != payable[1] else None,
    }


# Appending


async def _append(
    session: AsyncSession,
    investigation: Investigation,
    *,
    actor: str,
    actor_role: str | None,
    kind: EvidenceKind,
    summary: str,
    payload: dict[str, Any],
    key: str | None = None,
    alert_id: int | None = None,
) -> EvidenceEvent:
    at = datetime.now(UTC)
    body = to_json(payload)
    seq = investigation.event_count + 1
    digest = entry_hash(
        claim_id=investigation.claim_id,
        seq=seq,
        at=at,
        actor=actor,
        actor_role=actor_role,
        kind=kind.value,
        finding_key=key,
        alert_id=alert_id,
        summary=summary,
        payload=body,
        prev_hash=investigation.head_hash,
    )
    event = EvidenceEvent(
        claim_id=investigation.claim_id,
        seq=seq,
        at=at,
        actor=actor,
        actor_role=actor_role,
        kind=kind.value,
        finding_key=key,
        alert_id=alert_id,
        summary=summary,
        payload=body,
        prev_hash=investigation.head_hash,
        hash=digest,
    )
    session.add(event)
    investigation.event_count = seq
    investigation.head_hash = digest
    await session.flush()
    return event


async def _locked(session: AsyncSession, claim_id: str) -> Investigation | None:
    """The investigation row, locked so concurrent writers append one at a time."""
    return await session.scalar(select(Investigation).where(Investigation.claim_id == claim_id).with_for_update())


async def open_investigation(
    session: AsyncSession, claim_id: str, actor: str, actor_role: str | None = None
) -> Investigation:
    """Open the claim's investigation if it is not open yet. Idempotent and safe under concurrency."""
    if await session.get(Claim, claim_id) is None:
        raise not_found("Claim")
    await session.execute(
        pg_insert(Investigation)
        .values(claim_id=claim_id, opened_by=actor, event_count=0)
        .on_conflict_do_nothing(index_elements=["claim_id"])
    )
    investigation = await _locked(session, claim_id)
    assert investigation is not None
    if investigation.event_count == 0:
        snap = await snapshot(session, claim_id)
        totals = snap["totals"]
        await _append(
            session,
            investigation,
            actor=actor,
            actor_role=actor_role,
            kind=EvidenceKind.OPENED,
            summary=(
                f"Investigation opened with {totals['findings']} finding(s) and "
                f"{inr(totals['calculated_leakage'])} calculated leakage"
            ),
            payload=snap,
        )
    return investigation


async def _events(session: AsyncSession, claim_id: str) -> list[EvidenceEvent]:
    return list(
        await session.scalars(
            select(EvidenceEvent).where(EvidenceEvent.claim_id == claim_id).order_by(EvidenceEvent.seq)
        )
    )


def _latest_snapshot(events: list[EvidenceEvent]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.kind == EvidenceKind.OPENED.value:
            return event.payload
        if event.kind == EvidenceKind.RECALCULATED.value:
            return event.payload["snapshot"]
    return None


def original_findings(events: list[EvidenceEvent]) -> dict[str, dict[str, Any]]:
    """Each finding as first recorded: from the opening snapshot, or the recalculation that added it."""
    first: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.kind == EvidenceKind.OPENED.value:
            candidates = event.payload.get("findings", [])
        elif event.kind == EvidenceKind.RECALCULATED.value:
            candidates = event.payload["changes"]["added"]
        else:
            continue
        for f in candidates:
            first.setdefault(f["key"], f)
    return first


def latest_overrides(events: list[EvidenceEvent]) -> dict[str, dict[str, Any]]:
    current: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.kind == EvidenceKind.OVERRIDE.value and event.finding_key:
            current[event.finding_key] = {**event.payload, "seq": event.seq, "actor": event.actor, "at": event.at}
    return current


# Actions


async def record_decision(
    session: AsyncSession,
    alert: Alert,
    actor: str,
    previous: str,
    note: str | None,
    actor_role: str | None = None,
    extra: dict[str, Any] | None = None,
) -> EvidenceEvent:
    """Call after the alert's status is updated, in the same transaction."""
    investigation = await open_investigation(session, alert.claim_id, actor, actor_role)
    claim, lines, settlement = await _context(session, alert.claim_id)
    label = DECISION_LABELS.get(alert.status, alert.status.replace("_", " ").capitalize())
    return await _append(
        session,
        investigation,
        actor=actor,
        actor_role=actor_role,
        kind=EvidenceKind.DECISION,
        summary=f"{label}: {category_label(alert.category)}",
        payload={
            "previous": previous,
            "status": alert.status,
            "note": note,
            "finding": finding(alert, claim, lines, settlement),
            **(extra or {}),
        },
        key=finding_key(alert),
        alert_id=alert.id,
    )


async def override_correction(
    session: AsyncSession,
    claim_id: str,
    alert_id: int,
    correction: Decimal,
    reason: str,
    actor: str,
    actor_role: str | None = None,
) -> EvidenceEvent:
    """Change the recommended correction for one finding. The original recommendation stays on record."""
    alert = await session.get(Alert, alert_id)
    if alert is None or alert.claim_id != claim_id:
        raise not_found("Alert")
    investigation = await open_investigation(session, claim_id, actor, actor_role)
    claim, lines, settlement = await _context(session, claim_id)
    key = finding_key(alert)
    events = await _events(session, claim_id)
    current = recommendation(alert, claim, lines, settlement)
    original = original_findings(events).get(key, {}).get("recommendation") or to_json(current)
    ceiling = Decimal(str(original["original_amount"]))
    if correction > ceiling:
        raise AppError(
            422, "validation_error", f"The correction cannot be more than the original amount ({inr(ceiling)})"
        )
    previous = latest_overrides(events).get(key)
    previous_correction = previous["new_correction"] if previous else original["correction"]
    reverted = original["correction"] is not None and Decimal(str(original["correction"])) == correction
    before = "no amount" if previous_correction is None else inr(previous_correction)
    summary = (
        f"Correction restored to the recommended {inr(correction)}"
        if reverted
        else f"Correction changed from {before} to {inr(correction)}"
    )
    return await _append(
        session,
        investigation,
        actor=actor,
        actor_role=actor_role,
        kind=EvidenceKind.OVERRIDE,
        summary=f"{summary} ({category_label(alert.category)})",
        payload={
            "original_recommendation": original,
            "current_recommendation": current,
            "previous_correction": previous_correction,
            "new_correction": correction,
            "corrected_amount": max(Decimal("0"), ceiling - correction),
            "reason": reason,
            "reverted": reverted,
        },
        key=key,
        alert_id=alert.id,
    )


async def add_note(
    session: AsyncSession,
    claim_id: str,
    text: str,
    actor: str,
    actor_role: str | None = None,
    alert_id: int | None = None,
) -> EvidenceEvent:
    key = None
    if alert_id is not None:
        alert = await session.get(Alert, alert_id)
        if alert is None or alert.claim_id != claim_id:
            raise not_found("Alert")
        key = finding_key(alert)
    investigation = await open_investigation(session, claim_id, actor, actor_role)
    preview = text if len(text) <= 80 else text[:77] + "..."
    return await _append(
        session,
        investigation,
        actor=actor,
        actor_role=actor_role,
        kind=EvidenceKind.NOTE,
        summary=f"Note: {preview}",
        payload={"text": text},
        key=key,
        alert_id=alert_id,
    )


async def record_export(
    session: AsyncSession, claim_id: str, fmt: str, actor: str, actor_role: str | None = None
) -> EvidenceEvent:
    investigation = await open_investigation(session, claim_id, actor, actor_role)
    return await _append(
        session,
        investigation,
        actor=actor,
        actor_role=actor_role,
        kind=EvidenceKind.EXPORTED,
        summary=f"Investigation report downloaded ({fmt.upper()})",
        payload={"format": fmt, "events_covered": investigation.event_count},
    )


async def capture_rerun(session: AsyncSession, claim_ids: list[str], run_id: int) -> int:
    """After a run rewrites results, record what changed for every claim under investigation.
    Claims with no change get no entry. Returns the number of entries written."""
    written = 0
    for start in range(0, len(claim_ids), CHUNK):
        chunk = claim_ids[start : start + CHUNK]
        investigated = list(
            await session.scalars(select(Investigation.claim_id).where(Investigation.claim_id.in_(chunk)))
        )
        for claim_id in investigated:
            investigation = await _locked(session, claim_id)
            if investigation is None or investigation.event_count == 0:
                continue
            before = _latest_snapshot(await _events(session, claim_id)) or {}
            after = await snapshot(session, claim_id)
            changes = _changes(before, after)
            if not (changes["added"] or changes["removed"] or changes["changed"] or changes["payable"]):
                continue
            parts = [
                f"{len(changes['added'])} new" if changes["added"] else "",
                f"{len(changes['removed'])} resolved" if changes["removed"] else "",
                f"{len(changes['changed'])} changed" if changes["changed"] else "",
            ]
            detail = ", ".join(p for p in parts if p) or "payable changed"
            await _append(
                session,
                investigation,
                actor="system",
                actor_role=None,
                kind=EvidenceKind.RECALCULATED,
                summary=f"Run #{run_id} recalculated the claim: {detail}",
                payload={"run_id": run_id, "changes": changes, "snapshot": after},
            )
            written += 1
    return written


async def events_for(session: AsyncSession, claim_id: str) -> list[EvidenceEvent]:
    return await _events(session, claim_id)
