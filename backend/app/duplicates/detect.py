"""Duplicate detection: exact claims, duplicate lines, near-duplicates, and legitimate repeats (cleared).

Every claim in scope is compared with every other loaded claim (open and settled, same upload included).
When two records match, the earlier submission is the original and the later one is flagged.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from rapidfuzz.fuzz import ratio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ClaimStatus, MatchDecision, MatchSource, MatchType
from app.core.money import inr, q2
from app.db.models import Claim, LineItem, ServiceCode
from app.duplicates.normalise import normalise_reference
from app.rules.explain import d

NEAR_WINDOW_DAYS = 7
REPEAT_REFERENCE_SIMILARITY = Decimal("0.90")
DAILY_CATEGORIES = {"room", "icu"}


@dataclass(frozen=True)
class CodeRule:
    description: str
    repeatable: bool
    min_interval_days: int | None
    max_per_week: int | None


@dataclass
class ClaimView:
    claim: Claim
    lines: list[LineItem]
    settled_paid: tuple[Decimal, date] | None = None
    providers: frozenset[str] = field(default_factory=frozenset)
    references: frozenset[str] = field(default_factory=frozenset)

    @property
    def key(self) -> tuple[date, date, str]:
        return (self.claim.submission_date, self.claim.incident_date, self.claim.claim_id)

    @property
    def claimant(self) -> tuple[str, str]:
        return (self.claim.policy_number, self.claim.claimant_id)


def similarity(a: str | None, b: str | None) -> Decimal:
    if not a or not b:
        return Decimal(0)
    return q2(Decimal(str(ratio(a, b) / 100)))


def _views(loaded: dict[str, Any], settlements: dict[str, tuple[Decimal, date]]) -> list[ClaimView]:
    lines: dict[str, list[LineItem]] = defaultdict(list)
    for line in loaded["line_rows"]:
        lines[line.claim_id].append(line)
    views = []
    for claim in loaded["claim_rows"]:
        own = sorted(lines[claim.claim_id], key=lambda ln: ln.line_id)
        views.append(
            ClaimView(
                claim,
                own,
                settlements.get(claim.claim_id) if claim.status == ClaimStatus.SETTLED.value else None,
                frozenset(ln.provider_id for ln in own),
                frozenset(ln.invoice_reference_norm for ln in own if ln.invoice_reference_norm),
            )
        )
    return sorted(views, key=lambda v: v.key)


def _match(
    run_id: int,
    later: ClaimView,
    original: ClaimView,
    match_type: MatchType,
    decision: MatchDecision,
    reason: str,
    *,
    line: LineItem | None = None,
    matched_line: LineItem | None = None,
    score: Decimal | None = None,
    signals: dict | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "claim_id": later.claim.claim_id,
        "line_id": line.line_id if line else None,
        "matched_claim_id": original.claim.claim_id,
        "matched_line_id": matched_line.line_id if matched_line else None,
        "matched_source": (MatchSource.SETTLEMENT if original.settled_paid else MatchSource.CLAIM).value,
        "match_type": match_type.value,
        "score": score,
        "signals": signals,
        "decision": decision.value,
        "reason": reason,
    }


def _paid_note(original: ClaimView) -> str:
    if original.settled_paid:
        paid, when = original.settled_paid
        return f"; already paid {inr(paid)} on {d(when)}"
    return ""


def _exact(run_id: int, by_claimant: dict, flagged: set[str]) -> list[dict]:
    out = []
    for views in by_claimant.values():
        for i, later in enumerate(views):
            for original in views[:i]:
                if original.claim.claim_id in flagged:
                    continue
                same_invoices = (
                    later.references
                    and later.references == original.references
                    and later.providers == original.providers
                )
                c, o = later.claim, original.claim
                same_incident = (
                    c.incident_reference_norm
                    and c.incident_reference_norm == o.incident_reference_norm
                    and c.incident_date == o.incident_date
                    and c.requested_amount == o.requested_amount
                )
                if not (same_invoices or same_incident):
                    continue
                if same_invoices:
                    why = f"same claimant, provider and invoice(s) {', '.join(sorted(later.references))}"
                else:
                    why = (
                        f"same claimant, incident reference {c.incident_reference}, incident date "
                        f"{d(c.incident_date)} and amount {inr(c.requested_amount)}"
                    )
                reason = f"{c.claim_id} repeats {o.claim_id}: {why}{_paid_note(original)}."
                signals = {
                    "basis": "invoices" if same_invoices else "incident",
                    "requested_amount": str(c.requested_amount),
                }
                out.append(
                    _match(
                        run_id, later, original, MatchType.EXACT_CLAIM, MatchDecision.FLAGGED, reason, signals=signals
                    )
                )
                flagged.add(c.claim_id)
                break
    return out


def _lines(run_id: int, views: list[ClaimView], flagged: set[str]) -> list[dict]:
    out = []
    # Within a claim: same code, date, quantity and unit price (room and ICU lines therefore only on the same date).
    for view in views:
        if view.claim.claim_id in flagged:
            continue
        seen: dict[tuple, LineItem] = {}
        for line in view.lines:
            key = (line.service_code, line.service_date, line.quantity, line.unit_price)
            if key in seen:
                first = seen[key]
                reason = (
                    f"Line {line.line_id} repeats line {first.line_id} in the same claim: {line.service_description} "
                    f"on {d(line.service_date)}, {line.quantity.normalize():f} × {inr(line.unit_price)}."
                )
                signals = {"scope": "within_claim", "line_amount": str(line.line_amount)}
                out.append(
                    _match(
                        run_id,
                        view,
                        view,
                        MatchType.DUPLICATE_LINE,
                        MatchDecision.FLAGGED,
                        reason,
                        line=line,
                        matched_line=first,
                        signals=signals,
                    )
                )
            else:
                seen[key] = line
    # Across claims: same normalised invoice reference, code, date and amount.
    first_seen: dict[tuple, tuple[ClaimView, LineItem]] = {}
    for view in views:
        for line in view.lines:
            key = (line.invoice_reference_norm, line.service_code, line.service_date, line.line_amount)
            if key not in first_seen:
                first_seen[key] = (view, line)
                continue
            original, first = first_seen[key]
            if original is view or view.claim.claim_id in flagged:
                continue
            reason = (
                f"Line {line.line_id} in {view.claim.claim_id} repeats line {first.line_id} "
                f"in {original.claim.claim_id}: "
                f"invoice {line.invoice_reference}, {line.service_description} on {d(line.service_date)}, "
                f"{inr(line.line_amount)}{_paid_note(original)}."
            )
            signals = {"scope": "across_claims", "line_amount": str(line.line_amount)}
            out.append(
                _match(
                    run_id,
                    view,
                    original,
                    MatchType.DUPLICATE_LINE,
                    MatchDecision.FLAGGED,
                    reason,
                    line=line,
                    matched_line=first,
                    signals=signals,
                )
            )
    return out


def _dates(view: ClaimView) -> list[date]:
    return [view.claim.incident_date, *(ln.service_date for ln in view.lines)]


def _gap(a: ClaimView, b: ClaimView) -> int:
    return min(abs((x - y).days) for x in _dates(a) for y in _dates(b))


def _weekly_count(claimant_views: list[ClaimView], code: str, around: date) -> int:
    start, end = around - timedelta(days=3), around + timedelta(days=3)
    return sum(
        1 for v in claimant_views for ln in v.lines if ln.service_code == code and start <= ln.service_date <= end
    )


def _repeat_check(
    later: ClaimView,
    original: ClaimView,
    overlap: set[str],
    codes: dict[str, CodeRule],
    claimant_views: list[ClaimView],
) -> tuple[bool, bool, str]:
    """(is_repeat, too_frequent, reason). A repeat is cleared only when every overlapping code qualifies."""
    reasons = []
    reference_similarity = max(
        (similarity(a, b) for a in later.references for b in original.references), default=Decimal(0)
    )
    for code in sorted(overlap):
        rule = codes.get(code)
        if rule is None or not rule.repeatable:
            return False, False, ""
        later_dates = sorted(ln.service_date for ln in later.lines if ln.service_code == code)
        original_dates = sorted(ln.service_date for ln in original.lines if ln.service_code == code)
        gap = min(abs((a - b).days) for a in later_dates for b in original_dates)
        if gap == 0 or gap < (rule.min_interval_days or 0) or reference_similarity >= REPEAT_REFERENCE_SIMILARITY:
            return False, False, ""
        count = max(_weekly_count(claimant_views, code, day) for day in later_dates)
        if rule.max_per_week is not None and count > rule.max_per_week:
            return (
                True,
                True,
                (
                    f"{rule.description} {count} times in the 7 days around {d(later_dates[0])}, above the expected "
                    f"{rule.max_per_week} per week: frequency above expected."
                ),
            )
        reasons.append(
            f"{rule.description} on {d(original_dates[0])} and {d(later_dates[0])}: repeatable service, {gap}-day gap "
            f"meets the {rule.min_interval_days}-day minimum"
        )
    return True, False, "; ".join(reasons) + ", different invoices."


def _near(
    run_id: int, by_claimant: dict, flagged: set[str], codes: dict[str, CodeRule], threshold: Decimal
) -> list[dict]:
    out = []
    for views in by_claimant.values():
        for i, later in enumerate(views):
            if later.claim.claim_id in flagged:
                continue
            for original in views[:i]:
                if original.claim.claim_id in flagged or not (later.providers & original.providers):
                    continue
                gap = _gap(later, original)
                if gap > NEAR_WINDOW_DAYS:
                    continue
                later_codes = {ln.service_code for ln in later.lines}
                original_codes = {ln.service_code for ln in original.lines}
                overlap = later_codes & original_codes
                if not overlap:
                    continue
                is_repeat, too_frequent, repeat_reason = _repeat_check(later, original, overlap, codes, views)
                if is_repeat and not too_frequent:
                    line = next(ln for ln in later.lines if ln.service_code in overlap)
                    matched = next(ln for ln in original.lines if ln.service_code == line.service_code)
                    out.append(
                        _match(
                            run_id,
                            later,
                            original,
                            MatchType.LEGITIMATE_REPEAT,
                            MatchDecision.CLEARED,
                            repeat_reason,
                            line=line,
                            matched_line=matched,
                            signals={"date_gap_days": gap},
                        )
                    )
                    continue
                reference = max(
                    (similarity(a, b) for a in later.references for b in original.references), default=Decimal(0)
                )
                c, o = later.claim.requested_amount, original.claim.requested_amount
                amount_diff = q2(abs(c - o) / max(c, o)) if max(c, o) > 0 else Decimal(0)
                jaccard = q2(Decimal(len(overlap)) / Decimal(len(later_codes | original_codes)))
                score = q2(
                    Decimal("0.35") * reference
                    + Decimal("0.25") * (1 - Decimal(min(gap, NEAR_WINDOW_DAYS)) / NEAR_WINDOW_DAYS)
                    + Decimal("0.25") * (1 - min(amount_diff, Decimal("0.10")) / Decimal("0.10"))
                    + Decimal("0.15") * jaccard
                )
                overlapping = q2(sum((ln.line_amount for ln in later.lines if ln.service_code in overlap), Decimal(0)))
                signals = {
                    "reference_similarity": str(reference),
                    "references": [sorted(later.references), sorted(original.references)],
                    "date_gap_days": gap,
                    "amount_difference": str(amount_diff),
                    "code_overlap": str(jaccard),
                    "same_provider": True,
                    "overlapping_amount": str(overlapping),
                    "excess_frequency": too_frequent,
                }
                if too_frequent:
                    out.append(
                        _match(
                            run_id,
                            later,
                            original,
                            MatchType.NEAR_DUPLICATE,
                            MatchDecision.FLAGGED,
                            repeat_reason,
                            score=score,
                            signals=signals,
                        )
                    )
                    break
                if score >= threshold:
                    reason = (
                        f"{later.claim.claim_id} resembles {original.claim.claim_id} (score {score}): "
                        f"invoice similarity "
                        f"{reference}, {gap} day(s) apart, {q2(amount_diff * 100)}% amount difference, code overlap "
                        f"{jaccard}, same provider. Overlapping amount {inr(overlapping)} for review."
                    )
                    out.append(
                        _match(
                            run_id,
                            later,
                            original,
                            MatchType.NEAR_DUPLICATE,
                            MatchDecision.FLAGGED,
                            reason,
                            score=score,
                            signals=signals,
                        )
                    )
                    break
    return out


def find_duplicates(
    run_id: int,
    loaded: dict[str, Any],
    settlements: dict[str, tuple[Decimal, date]],
    codes: dict[str, CodeRule],
    threshold: Decimal,
) -> list[dict[str, Any]]:
    views = _views(loaded, settlements)
    by_claimant: dict[tuple[str, str], list[ClaimView]] = defaultdict(list)
    for view in views:
        by_claimant[view.claimant].append(view)
    flagged: set[str] = set()
    matches = _exact(run_id, by_claimant, flagged)
    matches += _lines(run_id, views, flagged)
    matches += _near(run_id, by_claimant, flagged, codes, threshold)
    return matches


async def detect_duplicates(
    session: AsyncSession, loaded: dict[str, Any], run_id: int, threshold: Decimal
) -> list[dict]:
    codes = {
        c.code: CodeRule(c.description, c.repeatable, c.min_interval_days, c.max_per_week)
        for c in await session.scalars(select(ServiceCode))
    }
    settlements = {
        claim.claim_id: (s.paid_amount, s.settlement_date)
        for policy_claims in loaded["claims"].values()
        for claim in policy_claims
        if (s := claim.settlement) is not None
    }
    return find_duplicates(run_id, loaded, settlements, codes, threshold)


__all__ = ["detect_duplicates", "find_duplicates", "normalise_reference", "similarity"]
