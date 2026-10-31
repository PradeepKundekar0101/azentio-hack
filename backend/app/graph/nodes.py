"""Graph nodes, one per distinct entity keyed on normalised identifiers, and the structural claim-to-entity edges.

Node IDs are "<node_type>:<node_key>": claim:CLM-000123, policy:POL-000045, claimant:MEM-000310,
provider:PRV-0012, invoice:PRV-0012|INV452, incident:ADM881, document:<sha256>. Near-identical images
(perceptual-hash distance within NEAR_IDENTICAL_DISTANCE) share one document node, keyed on the first one's SHA-256.
"""

from dataclasses import dataclass
from typing import Any

from app.core.enums import NodeType
from app.documents.phash import phash_distance
from app.graph.edges import PHASH_MAX_DISTANCE, DocInfo, GraphInputs

HUB_TYPES = {NodeType.PROVIDER.value, NodeType.POLICY.value}  # shown, never traversed to relate claims


@dataclass
class Node:
    node_id: str
    node_type: str
    node_key: str
    label: str
    attributes: dict[str, Any]


@dataclass
class Structural:
    claim_id: str
    to_node: str
    edge_type: str
    evidence: dict[str, Any]


def node_id(node_type: NodeType | str, key: str) -> str:
    return f"{NodeType(node_type).value}:{key}"


def document_keys(documents: list[DocInfo]) -> dict[int, str]:
    """document_id -> node key: identical files share their SHA-256; near-identical images join the first image."""
    keys: dict[int, str] = {}
    images: list[DocInfo] = []
    for doc in sorted(documents, key=lambda d: d.document_id):
        key = doc.sha256
        if doc.phash:
            for seen in images:
                if seen.phash and phash_distance(seen.phash, doc.phash) <= PHASH_MAX_DISTANCE:
                    key = keys[seen.document_id]
                    break
            images.append(doc)
        keys[doc.document_id] = key
    return keys


def build_nodes(data: GraphInputs) -> tuple[dict[str, Node], list[Structural]]:
    nodes: dict[str, Node] = {}
    edges: list[Structural] = []

    def add(node_type: NodeType, key: str, label: str, **attributes: Any) -> str:
        nid = node_id(node_type, key)
        if nid not in nodes:
            nodes[nid] = Node(nid, node_type.value, key, label, attributes)
        return nid

    def link(claim_id: str, to: str, edge_type: str, field: str, value: object) -> None:
        edges.append(Structural(claim_id, to, edge_type, {"fields": [field], "values": {field: value}}))

    for c in data.claims:
        add(
            NodeType.CLAIM,
            c.claim_id,
            c.claim_id,
            policy_number=c.policy_number,
            claimant_id=c.claimant_id,
            claim_type=c.claim_type,
            status=c.status,
            requested_amount=str(c.requested_amount),
            incident_date=c.incident_date.isoformat(),
        )
        link(
            c.claim_id,
            add(NodeType.POLICY, c.policy_number, c.policy_number),
            "filed_under",
            "policy_number",
            c.policy_number,
        )
        claimant = add(NodeType.CLAIMANT, c.claimant_id, c.claimant_name, policy_number=c.policy_number)
        link(c.claim_id, claimant, "claimed_by", "claimant_id", c.claimant_id)
        if c.incident_reference_norm:
            incident = add(
                NodeType.INCIDENT, c.incident_reference_norm, c.incident_reference or c.incident_reference_norm
            )
            link(c.claim_id, incident, "for_incident", "incident_reference", c.incident_reference)

    seen: set[tuple[str, str]] = set()
    for ln in data.lines:
        provider = add(NodeType.PROVIDER, ln.provider_id, ln.provider_name)
        invoice = add(
            NodeType.INVOICE,
            f"{ln.provider_id}|{ln.invoice_reference_norm}",
            ln.invoice_reference,
            provider_id=ln.provider_id,
        )
        for to, edge_type, field, value in (
            (provider, "treated_at", "provider_id", ln.provider_id),
            (invoice, "billed_on", "invoice_reference", ln.invoice_reference),
        ):
            if (ln.claim_id, to) not in seen:
                seen.add((ln.claim_id, to))
                link(ln.claim_id, to, edge_type, field, value)

    keys = document_keys(data.documents)
    for doc in data.documents:
        document = add(NodeType.DOCUMENT, keys[doc.document_id], doc.file_name)
        if (doc.claim_id, document) not in seen:
            seen.add((doc.claim_id, document))
            link(doc.claim_id, document, "supported_by", "sha256", doc.sha256)
    return nodes, edges
