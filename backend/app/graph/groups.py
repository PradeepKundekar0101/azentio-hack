"""Related-claim groups: connected components of the claim graph built from strong links, plus weak links only where a
pair has two or more of them. A group's ID derives from its sorted claim IDs, so unchanged membership keeps its ID."""

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

import networkx as nx

from app.core.enums import EdgeStrength, GroupTag
from app.core.money import inr
from app.graph.edges import ClaimInfo, Link

MIN_WEAK_LINKS = 2
# The order tags are mentioned in a summary: the most specific first.
TAG_ORDER = [
    GroupTag.INVOICE_REUSED_ACROSS_POLICIES.value,
    GroupTag.DOCUMENT_REUSED.value,
    GroupTag.INCIDENT_CLAIMED_TWICE.value,
    GroupTag.CONCURRENT_STAYS.value,
    GroupTag.DUPLICATE_CLUSTER.value,
    GroupTag.WEAK_PATTERN.value,
]


def group_id(claim_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(claim_ids)).encode()).hexdigest()
    return f"REL-{digest[:10].upper()}"


@dataclass
class Group:
    group_id: str
    claim_ids: list[str]
    tags: list[str]
    policy_count: int
    total_requested: Decimal
    summary: str
    links: list[Link]

    def content_hash(self) -> str:
        parts = [",".join(self.claim_ids), ",".join(self.tags), str(self.total_requested), self.summary]
        parts += [f"{x.a}>{x.b}:{x.link_type}" for x in self.links]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def included_links(links: list[Link]) -> list[Link]:
    """Strong links, and the weak links of pairs that have at least two kinds of weak link."""
    weak_kinds: dict[tuple[str, str], set[str]] = defaultdict(set)
    for link in links:
        if link.strength == EdgeStrength.WEAK.value:
            weak_kinds[link.pair].add(link.link_type)
    return [
        link
        for link in links
        if link.strength == EdgeStrength.STRONG.value or len(weak_kinds[link.pair]) >= MIN_WEAK_LINKS
    ]


def short_name(name: str) -> str:
    """'Ravi Kumar' -> 'R. Kumar'."""
    parts = name.split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) > 1 else name


def _who(claim: ClaimInfo) -> str:
    return f"{claim.claim_id} under {claim.policy_number} ({short_name(claim.claimant_name)})"


def summarise(claims: dict[str, ClaimInfo], members: list[str], tags: list[str], links: list[Link]) -> str:
    """One templated sentence about the strongest connection, then the group's size and amount."""
    total = sum((claims[c].requested_amount for c in members), Decimal(0))
    policies = len({claims[c].policy_number for c in members})
    tail = (
        f"{len(members)} claims under {policies} {'policy' if policies == 1 else 'policies'}, {inr(total)} requested."
    )
    lead = tags[0]
    link = next(x for x in links if x.tag == lead)
    a, b = claims[link.a], claims[link.b]
    values = link.evidence["values"]
    if link.link_type == "shared_invoice":
        ref = values["invoice_reference"][link.a]
        amounts = {cid: sum((Decimal(v) for v in values["line_amounts"][cid]), Decimal(0)) for cid in (link.a, link.b)}
        same = amounts[link.a] == amounts[link.b]
        bills = (
            f"both bill {inr(amounts[link.a])}"
            if same
            else f"billing {inr(amounts[link.a])} and {inr(amounts[link.b])}"
        )
        sentence = (
            f"Invoice {ref} from {values['provider_name']} ({values['provider_id']}) appears in {_who(a)} "
            f"and {_who(b)}; {bills}."
        )
    elif link.link_type == "shared_incident":
        ref = values["incident_reference"][link.a]
        sentence = f"Incident {ref} of {a.incident_date:%d %b %Y} is claimed in {_who(a)} and {_who(b)}."
    elif link.link_type == "shared_document":
        files = values["file_names"]
        how = (
            "the same file"
            if values["hash_distance"] == 0
            else f"a near-identical image (distance {values['hash_distance']})"
        )
        sentence = f"{_who(a)} and {_who(b)} attach {how}: {files[link.a]} and {files[link.b]}."
    elif link.link_type == "overlapping_stays":
        periods = values["periods"]
        sentence = (
            f"{short_name(a.claimant_name)} ({a.claimant_id}) was in hospital at two providers at once: "
            f"{link.a} from {periods[link.a][0]} to {periods[link.a][1]} and {link.b} from {periods[link.b][0]} "
            f"to {periods[link.b][1]}."
        )
    elif link.link_type == "duplicate_match":
        kind = "an exact duplicate" if values["match_type"] == "exact_claim" else "a near-duplicate"
        sentence = f"{link.b} is {kind} of {link.a} ({short_name(a.claimant_name)}, {a.policy_number})."
    else:
        kinds = sorted({x.link_type.replace("_", " ") for x in links if x.pair == link.pair})
        sentence = f"{_who(a)} and {_who(b)} share several weak signals: {', '.join(kinds)}."
    return f"{sentence} {tail}"


def build_groups(claims: dict[str, ClaimInfo], links: list[Link]) -> list[Group]:
    kept = included_links(links)
    graph = nx.Graph()
    graph.add_edges_from(link.pair for link in kept)
    groups = []
    for component in nx.connected_components(graph):
        members = sorted(component)
        if len(members) < 2:
            continue
        own = [x for x in kept if x.a in component]
        present = {x.tag for x in own}
        strong = any(x.strength == EdgeStrength.STRONG.value for x in own)
        if strong:  # a group with a strong connection is not called a weak pattern
            present.discard(GroupTag.WEAK_PATTERN.value)
        tags = [t for t in TAG_ORDER if t in present]
        groups.append(
            Group(
                group_id=group_id(members),
                claim_ids=members,
                tags=tags,
                policy_count=len({claims[c].policy_number for c in members}),
                total_requested=sum((claims[c].requested_amount for c in members), Decimal(0)),
                summary=summarise(claims, members, tags, own),
                links=own,
            )
        )
    return sorted(groups, key=lambda g: g.group_id)
