"""Claim-to-claim link rules. Claims are related only through these specific rules, never by sharing a provider or a
policy (the hub rule), and every link carries the exact fields and values that matched. No link comes from the LLM.

Strong links: a shared invoice, a shared incident reference, a shared bill document, a flagged exact or near
duplicate, and overlapping hospital stays of one claimant at different providers.
Weak links: same claimant and provider within 7 days, same policy and provider within 7 days (different claimants),
and amounts within 2% at the same provider within 30 days. A pair counts only with two or more weak links.
Pairs cleared as legitimate repeats never link.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Any

from app.core.enums import EdgeStrength, GroupTag, MatchDecision, MatchType
from app.documents.phash import NEAR_IDENTICAL_DISTANCE, phash_distance

WEAK_WINDOW_DAYS = 7
AMOUNT_WINDOW_DAYS = 30
AMOUNT_TOLERANCE = Decimal("0.02")
PHASH_MAX_DISTANCE = NEAR_IDENTICAL_DISTANCE
FLAGGED_DUPLICATES = {MatchType.EXACT_CLAIM.value, MatchType.NEAR_DUPLICATE.value}


@dataclass(frozen=True)
class ClaimInfo:
    claim_id: str
    policy_number: str
    claimant_id: str
    claimant_name: str
    incident_date: date
    submission_date: date
    claim_type: str
    requested_amount: Decimal
    incident_reference: str | None
    incident_reference_norm: str | None
    status: str


@dataclass(frozen=True)
class LineInfo:
    line_id: str
    claim_id: str
    invoice_reference: str
    invoice_reference_norm: str
    provider_id: str
    provider_name: str
    service_date: date
    service_code: str
    line_amount: Decimal


@dataclass(frozen=True)
class DocInfo:
    document_id: int
    claim_id: str
    file_name: str
    sha256: str
    phash: str | None


@dataclass(frozen=True)
class MatchInfo:
    claim_id: str
    matched_claim_id: str
    match_type: str
    decision: str
    score: Decimal | None


@dataclass
class GraphInputs:
    claims: list[ClaimInfo]
    lines: list[LineInfo]
    documents: list[DocInfo] = field(default_factory=list)
    matches: list[MatchInfo] = field(default_factory=list)


@dataclass
class Link:
    a: str  # the lower claim ID
    b: str
    link_type: str
    strength: str
    tag: str
    evidence: dict[str, Any]
    score: Decimal | None = None

    @property
    def pair(self) -> tuple[str, str]:
        return self.a, self.b


def _pair(x: str, y: str) -> tuple[str, str]:
    return (x, y) if x < y else (y, x)


def _iso(value: date) -> str:
    return value.isoformat()


class _Context:
    def __init__(self, data: GraphInputs) -> None:
        self.claims = {c.claim_id: c for c in data.claims}
        self.lines: dict[str, list[LineInfo]] = defaultdict(list)
        for line in data.lines:
            if line.claim_id in self.claims:
                self.lines[line.claim_id].append(line)
        self.cleared = {
            _pair(m.claim_id, m.matched_claim_id)
            for m in data.matches
            if m.decision == MatchDecision.CLEARED.value or m.match_type == MatchType.LEGITIMATE_REPEAT.value
        }
        self.period = {
            cid: (min(ln.service_date for ln in items), max(ln.service_date for ln in items))
            for cid, items in self.lines.items()
        }
        self.providers = {cid: {ln.provider_id for ln in items} for cid, items in self.lines.items()}

    def cross_policy(self, a: str, b: str) -> bool:
        return self.claims[a].policy_number != self.claims[b].policy_number


def _shared_invoices(ctx: _Context) -> list[Link]:
    by_invoice: dict[tuple[str, str], dict[str, list[LineInfo]]] = defaultdict(lambda: defaultdict(list))
    for cid, items in ctx.lines.items():
        for line in items:
            by_invoice[(line.provider_id, line.invoice_reference_norm)][cid].append(line)
    links = []
    for (provider_id, _), owners in by_invoice.items():
        for x, y in combinations(sorted(owners), 2):
            a, b = _pair(x, y)
            written = {cid: owners[cid][0].invoice_reference for cid in (a, b)}
            links.append(
                Link(
                    a,
                    b,
                    "shared_invoice",
                    EdgeStrength.STRONG.value,
                    GroupTag.INVOICE_REUSED_ACROSS_POLICIES.value
                    if ctx.cross_policy(a, b)
                    else GroupTag.DUPLICATE_CLUSTER.value,
                    {
                        "fields": ["provider_id", "invoice_reference"],
                        "values": {
                            "provider_id": provider_id,
                            "provider_name": owners[a][0].provider_name,
                            "invoice_reference": written,
                            "line_amounts": {cid: [str(ln.line_amount) for ln in owners[cid]] for cid in (a, b)},
                            "policies": {cid: ctx.claims[cid].policy_number for cid in (a, b)},
                        },
                        "source_records": {"line_ids": {cid: [ln.line_id for ln in owners[cid]] for cid in (a, b)}},
                    },
                )
            )
    return links


def _shared_incidents(ctx: _Context) -> list[Link]:
    by_incident: dict[str, list[str]] = defaultdict(list)
    for claim in ctx.claims.values():
        if claim.incident_reference_norm:
            by_incident[claim.incident_reference_norm].append(claim.claim_id)
    links = []
    for owners in by_incident.values():
        for x, y in combinations(sorted(owners), 2):
            a, b = _pair(x, y)
            ca, cb = ctx.claims[a], ctx.claims[b]
            links.append(
                Link(
                    a,
                    b,
                    "shared_incident",
                    EdgeStrength.STRONG.value,
                    GroupTag.INCIDENT_CLAIMED_TWICE.value
                    if ctx.cross_policy(a, b)
                    else GroupTag.DUPLICATE_CLUSTER.value,
                    {
                        "fields": ["incident_reference"],
                        "values": {
                            "incident_reference": {a: ca.incident_reference, b: cb.incident_reference},
                            "incident_dates": {a: _iso(ca.incident_date), b: _iso(cb.incident_date)},
                            "policies": {a: ca.policy_number, b: cb.policy_number},
                            "requested_amounts": {a: str(ca.requested_amount), b: str(cb.requested_amount)},
                        },
                        "source_records": {"claim_ids": [a, b]},
                    },
                )
            )
    return links


def _shared_documents(ctx: _Context, documents: list[DocInfo]) -> list[Link]:
    docs = [d for d in documents if d.claim_id in ctx.claims]
    best: dict[tuple[str, str], tuple[int, DocInfo, DocInfo]] = {}
    for x, y in combinations(docs, 2):
        if x.claim_id == y.claim_id:
            continue
        if x.sha256 == y.sha256:
            distance = 0
        elif x.phash and y.phash:  # near-identical images (re-scans, re-saves)
            distance = phash_distance(x.phash, y.phash)
            if distance > PHASH_MAX_DISTANCE:
                continue
        else:
            continue
        key = _pair(x.claim_id, y.claim_id)
        if key not in best or distance < best[key][0]:
            first, second = (x, y) if x.claim_id == key[0] else (y, x)
            best[key] = (distance, first, second)
    links = []
    for (a, b), (distance, da, db) in sorted(best.items()):
        exact = distance == 0 and da.sha256 == db.sha256
        links.append(
            Link(
                a,
                b,
                "shared_document",
                EdgeStrength.STRONG.value,
                GroupTag.DOCUMENT_REUSED.value,
                {
                    "fields": ["sha256"] if exact else ["phash"],
                    "values": {
                        "sha256": {a: da.sha256, b: db.sha256},
                        "phash": {a: da.phash, b: db.phash},
                        "hash_distance": distance,
                        "file_names": {a: da.file_name, b: db.file_name},
                    },
                    "source_records": {"document_ids": {a: da.document_id, b: db.document_id}},
                },
            )
        )
    return links


def _duplicates(ctx: _Context, matches: list[MatchInfo]) -> list[Link]:
    links: dict[tuple[str, str], Link] = {}
    for m in matches:
        if m.decision != MatchDecision.FLAGGED.value or m.match_type not in FLAGGED_DUPLICATES:
            continue
        if m.claim_id not in ctx.claims or m.matched_claim_id not in ctx.claims:
            continue
        a, b = _pair(m.claim_id, m.matched_claim_id)
        links[(a, b)] = Link(
            a,
            b,
            "duplicate_match",
            EdgeStrength.STRONG.value,
            GroupTag.DUPLICATE_CLUSTER.value,
            {
                "fields": ["match_type", "score"],
                "values": {"match_type": m.match_type, "score": str(m.score) if m.score is not None else None},
                "source_records": {"claim_id": m.claim_id, "matched_claim_id": m.matched_claim_id},
            },
            m.score,
        )
    return list(links.values())


def _overlapping_stays(ctx: _Context) -> list[Link]:
    """Hospital stays of one claimant at different providers whose service periods overlap."""
    by_claimant: dict[str, list[str]] = defaultdict(list)
    for claim in ctx.claims.values():
        if claim.claim_type == "inpatient" and claim.claim_id in ctx.period:
            by_claimant[claim.claimant_id].append(claim.claim_id)
    links = []
    for owners in by_claimant.values():
        for x, y in combinations(sorted(owners), 2):
            (sa, ea), (sb, eb) = ctx.period[x], ctx.period[y]
            if sa > eb or sb > ea or ctx.providers[x] & ctx.providers[y]:
                continue
            a, b = _pair(x, y)
            links.append(
                Link(
                    a,
                    b,
                    "overlapping_stays",
                    EdgeStrength.STRONG.value,
                    GroupTag.CONCURRENT_STAYS.value,
                    {
                        "fields": ["claimant_id", "periods"],
                        "values": {
                            "claimant_id": ctx.claims[a].claimant_id,
                            "periods": {cid: [_iso(ctx.period[cid][0]), _iso(ctx.period[cid][1])] for cid in (a, b)},
                            "providers": {cid: sorted(ctx.providers[cid]) for cid in (a, b)},
                        },
                        "source_records": {"claim_ids": [a, b]},
                    },
                )
            )
    return links


def _weak(ctx: _Context) -> list[Link]:
    by_provider: dict[str, list[str]] = defaultdict(list)
    for cid, providers in ctx.providers.items():
        for provider in providers:
            by_provider[provider].append(cid)
    links = []
    for provider, owners in by_provider.items():
        ordered = sorted(owners, key=lambda cid: (ctx.period[cid][0], cid))
        for i, x in enumerate(ordered):
            for y in ordered[i + 1 :]:
                gap = (ctx.period[y][0] - ctx.period[x][0]).days
                if gap > AMOUNT_WINDOW_DAYS:
                    break
                a, b = _pair(x, y)
                ca, cb = ctx.claims[a], ctx.claims[b]
                dates = {a: _iso(ctx.period[a][0]), b: _iso(ctx.period[b][0])}
                base = {"provider_id": provider, "service_dates": dates, "gap_days": gap}
                if gap <= WEAK_WINDOW_DAYS and ca.claimant_id == cb.claimant_id:
                    links.append(
                        _weak_link(
                            a,
                            b,
                            "same_claimant_provider",
                            ["claimant_id", "provider_id", "service_dates"],
                            {**base, "claimant_id": ca.claimant_id},
                        )
                    )
                elif gap <= WEAK_WINDOW_DAYS and ca.policy_number == cb.policy_number:
                    links.append(
                        _weak_link(
                            a,
                            b,
                            "same_policy_provider",
                            ["policy_number", "provider_id", "service_dates"],
                            {
                                **base,
                                "policy_number": ca.policy_number,
                                "claimants": {a: ca.claimant_id, b: cb.claimant_id},
                            },
                        )
                    )
                high = max(ca.requested_amount, cb.requested_amount)
                if high > 0 and abs(ca.requested_amount - cb.requested_amount) <= high * AMOUNT_TOLERANCE:
                    links.append(
                        _weak_link(
                            a,
                            b,
                            "similar_amount",
                            ["provider_id", "requested_amount"],
                            {**base, "requested_amount": {a: str(ca.requested_amount), b: str(cb.requested_amount)}},
                        )
                    )
    return links


def _weak_link(a: str, b: str, link_type: str, fields: list[str], values: dict[str, Any]) -> Link:
    return Link(
        a,
        b,
        link_type,
        EdgeStrength.WEAK.value,
        GroupTag.WEAK_PATTERN.value,
        {"fields": fields, "values": values, "source_records": {"claim_ids": [a, b]}},
    )


def claim_links(data: GraphInputs) -> list[Link]:
    """Every claim-to-claim link, in a deterministic order."""
    ctx = _Context(data)
    links = (
        _shared_invoices(ctx)
        + _shared_incidents(ctx)
        + _shared_documents(ctx, data.documents)
        + _duplicates(ctx, data.matches)
        + _overlapping_stays(ctx)
        + _weak(ctx)
    )
    # One link per pair and type (a claim billed at two providers meets its neighbours once per provider).
    unique: dict[tuple[str, str, str], Link] = {}
    for link in links:
        if link.pair not in ctx.cleared:
            unique.setdefault((link.a, link.b, link.link_type), link)
    return [unique[k] for k in sorted(unique)]
