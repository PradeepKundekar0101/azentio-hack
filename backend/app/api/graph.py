"""Correlation graph API: rebuild, related-claim groups, a claim's related subgraph and the records behind a node."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.claims import LineOut
from app.api.pagination import Page, PageDep
from app.core.config import Settings
from app.core.enums import EdgeStrength, NodeType
from app.core.errors import AppError, not_found
from app.core.security import session_principal
from app.db.models import Claim, Document, GraphBuild, GraphEdge, GraphNode, LineItem, RelationshipGroup
from app.db.session import SessionDep
from app.graph.nodes import HUB_TYPES
from app.graph.service import build_graph, latest_build_id

router = APIRouter(tags=["graph"], dependencies=[Depends(session_principal)])
MAX_SUBGRAPH_CLAIMS = 60
MAX_NODE_CLAIMS = 200


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RebuildIn(BaseModel):
    claim_ids: list[str] | None = Field(default=None, max_length=10000)


class BuildOut(Orm):
    build_id: int
    started_at: datetime
    finished_at: datetime | None
    scope: dict[str, Any]
    node_count: int
    edge_count: int
    group_count: int


class GroupOut(Orm):
    group_id: str
    version: int
    build_id: int
    claim_ids: list[str]
    policy_count: int
    tags: list[str]
    total_requested: Decimal
    summary: str
    created_at: datetime


class NodeOut(Orm):
    node_id: str
    node_type: str
    node_key: str
    label: str
    attributes: dict[str, Any] | None
    # Provider and policy nodes are hubs: shown, never expanded to the claims behind them.
    expanded: bool = True


class EdgeOut(Orm):
    edge_id: int
    from_node: str
    to_node: str
    edge_type: str
    strength: str
    evidence: dict[str, Any] | None
    score: Decimal | None
    # Edges come from the link rules only; the LLM never creates one.
    generated_by: Literal["rule"] = "rule"


class MemberOut(Orm):
    claim_id: str
    policy_number: str
    claimant_id: str
    claimant_name: str
    claim_type: str
    status: str
    incident_date: date
    submission_date: date
    requested_amount: Decimal


class GroupDetail(GroupOut):
    members: list[MemberOut]
    edges: list[EdgeOut]


class RelatedOut(BaseModel):
    claim_id: str
    build_id: int | None
    groups: list[GroupOut]
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class DocumentRef(Orm):
    id: int
    claim_id: str | None
    file_name: str
    sha256: str
    phash: str | None


class NodeRecords(BaseModel):
    node: NodeOut
    claims: list[MemberOut]
    lines: list[LineOut]
    documents: list[DocumentRef]
    truncated: bool


@router.post("/graph/rebuild")
async def rebuild(body: RebuildIn, request: Request, session: SessionDep) -> BuildOut:
    settings: Settings = request.app.state.settings
    build = await build_graph(session, settings, claim_ids=body.claim_ids)
    await session.commit()
    return BuildOut.model_validate(build)


async def _current_groups(session: AsyncSession) -> tuple[int | None, list[RelationshipGroup]]:
    build_id = await latest_build_id(session)
    if build_id is None:
        return None, []
    build = await session.get(GraphBuild, build_id)
    refs = [(r["group_id"], r["version"]) for r in (build.groups or [])] if build else []
    if not refs:
        return build_id, []
    rows = await session.scalars(
        select(RelationshipGroup)
        .where(tuple_(RelationshipGroup.group_id, RelationshipGroup.version).in_(refs))
        .order_by(RelationshipGroup.group_id)
    )
    return build_id, list(rows)


@router.get("/relationship-groups")
async def list_groups(
    session: SessionDep,
    page: PageDep,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    min_claims: Annotated[int | None, Query(ge=2)] = None,
    min_policies: Annotated[int | None, Query(ge=1)] = None,
    min_amount: Annotated[Decimal | None, Query(ge=0)] = None,
) -> Page[GroupOut]:
    _, groups = await _current_groups(session)
    kept = [
        g
        for g in groups
        if (tag is None or tag in g.tags)
        and (min_claims is None or len(g.claim_ids) >= min_claims)
        and (min_policies is None or g.policy_count >= min_policies)
        and (min_amount is None or g.total_requested >= min_amount)
    ]
    kept.sort(key=lambda g: (-g.total_requested, g.group_id))
    items = kept[page.offset : page.offset + page.page_size]
    return Page(items=[GroupOut.model_validate(g) for g in items], total=len(kept))


async def _members(session: AsyncSession, claim_ids: list[str]) -> list[MemberOut]:
    rows = await session.scalars(select(Claim).where(Claim.claim_id.in_(claim_ids)).order_by(Claim.claim_id))
    return [MemberOut.model_validate(c) for c in rows]


async def _claim_edges(session: AsyncSession, build_id: int, claim_ids: list[str]) -> list[GraphEdge]:
    nodes = [f"claim:{cid}" for cid in claim_ids]
    rows = await session.scalars(
        select(GraphEdge)
        .where(
            GraphEdge.build_id == build_id,
            GraphEdge.strength != EdgeStrength.STRUCTURAL.value,
            GraphEdge.from_node.in_(nodes),
            GraphEdge.to_node.in_(nodes),
        )
        .order_by(GraphEdge.edge_id)
    )
    return list(rows)


@router.get("/relationship-groups/{group_id}")
async def group_detail(
    group_id: str, session: SessionDep, version: Annotated[int | None, Query(ge=1)] = None
) -> GroupDetail:
    if version is None:
        build_id, groups = await _current_groups(session)
        group = next((g for g in groups if g.group_id == group_id), None)
        if group is None:  # no longer current: show its latest version
            group = await session.scalar(
                select(RelationshipGroup)
                .where(RelationshipGroup.group_id == group_id)
                .order_by(RelationshipGroup.version.desc())
                .limit(1)
            )
            build_id = group.build_id if group else None
    else:
        group = await session.get(RelationshipGroup, (group_id, version))
        build_id = group.build_id if group else None
    if group is None or build_id is None:
        raise not_found("Relationship group")
    edges = await _claim_edges(session, build_id, list(group.claim_ids))
    return GroupDetail(
        **GroupOut.model_validate(group).model_dump(),
        members=await _members(session, list(group.claim_ids)),
        edges=[EdgeOut.model_validate(e) for e in edges],
    )


@router.get("/claims/{claim_id}/related")
async def related(claim_id: str, session: SessionDep) -> RelatedOut:
    """The claim's groups and its subgraph: entities up to two hops away, with hubs shown but not expanded."""
    if await session.get(Claim, claim_id) is None:
        raise not_found("Claim")
    build_id, groups = await _current_groups(session)
    mine = [g for g in groups if claim_id in g.claim_ids]
    if build_id is None:
        return RelatedOut(claim_id=claim_id, build_id=None, groups=[], nodes=[], edges=[])
    start = f"claim:{claim_id}"
    claims = {start} | {f"claim:{cid}" for g in mine for cid in g.claim_ids}
    first_hop = list(
        await session.scalars(
            select(GraphEdge).where(
                GraphEdge.build_id == build_id,
                GraphEdge.strength == EdgeStrength.STRUCTURAL.value,
                GraphEdge.from_node.in_(claims),
            )
        )
    )
    node_types = {e.to_node: e.to_node.split(":", 1)[0] for e in first_hop}
    expandable = [n for n, t in node_types.items() if t not in HUB_TYPES]
    second_hop = list(
        await session.scalars(
            select(GraphEdge)
            .where(
                GraphEdge.build_id == build_id,
                GraphEdge.strength == EdgeStrength.STRUCTURAL.value,
                GraphEdge.to_node.in_(expandable),
            )
            .order_by(GraphEdge.edge_id)
            .limit(MAX_SUBGRAPH_CLAIMS * 4)
        )
    )
    claims |= {e.from_node for e in second_hop}
    claim_links = await _claim_edges(session, build_id, [c.split(":", 1)[1] for c in claims])
    edges = {e.edge_id: e for e in (*first_hop, *second_hop, *claim_links)}
    node_ids = claims | {e.to_node for e in edges.values()}
    nodes = await session.scalars(select(GraphNode).where(GraphNode.node_id.in_(node_ids)).order_by(GraphNode.node_id))
    node_out = []
    for node in nodes:
        out = NodeOut.model_validate(node)
        out.expanded = node.node_type not in HUB_TYPES
        node_out.append(out)
    return RelatedOut(
        claim_id=claim_id,
        build_id=build_id,
        groups=[GroupOut.model_validate(g) for g in mine],
        nodes=node_out,
        edges=[EdgeOut.model_validate(e) for e in sorted(edges.values(), key=lambda e: e.edge_id)],
    )


@router.get("/graph/nodes/{node_id:path}/records")
async def node_records(node_id: str, session: SessionDep) -> NodeRecords:
    """The records behind a node: its claims, their lines (only the invoice's lines for an invoice) and documents."""
    node = await session.get(GraphNode, node_id)
    if node is None:
        raise not_found("Graph node")
    build_id = await latest_build_id(session)
    if build_id is None:
        raise AppError(409, "no_graph", "The graph has not been built yet")
    if node.node_type == NodeType.CLAIM.value:
        claim_ids = [node.node_key]
    else:
        claim_ids = [
            e.split(":", 1)[1]
            for e in await session.scalars(
                select(GraphEdge.from_node)
                .where(GraphEdge.build_id == build_id, GraphEdge.to_node == node_id)
                .order_by(GraphEdge.from_node)
                .limit(MAX_NODE_CLAIMS + 1)
            )
        ]
    truncated = len(claim_ids) > MAX_NODE_CLAIMS
    claim_ids = claim_ids[:MAX_NODE_CLAIMS]
    line_query = select(LineItem).where(LineItem.claim_id.in_(claim_ids))
    if node.node_type == NodeType.INVOICE.value:
        provider_id, reference = node.node_key.split("|", 1)
        line_query = line_query.where(LineItem.provider_id == provider_id, LineItem.invoice_reference_norm == reference)
    elif node.node_type == NodeType.PROVIDER.value:
        line_query = line_query.where(LineItem.provider_id == node.node_key)
    lines = await session.scalars(line_query.order_by(LineItem.claim_id, LineItem.line_id))
    doc_query = select(Document).where(Document.claim_id.in_(claim_ids))
    if node.node_type == NodeType.DOCUMENT.value:
        doc_query = select(Document).where(
            or_(Document.sha256 == node.node_key, Document.claim_id.in_(claim_ids)), Document.claim_id.is_not(None)
        )
    documents = await session.scalars(doc_query.order_by(Document.id))
    out = NodeOut.model_validate(node)
    out.expanded = node.node_type not in HUB_TYPES
    return NodeRecords(
        node=out,
        claims=await _members(session, claim_ids),
        lines=[LineOut.model_validate(ln) for ln in lines],
        documents=[DocumentRef.model_validate(d) for d in documents],
        truncated=truncated,
    )
