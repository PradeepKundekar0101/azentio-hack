"""Build the correlation graph from the database and store it as one append-only build: nodes (upserted entities),
structural and claim-to-claim edges, new versions of changed groups, cross-claim alerts and analysis events.

Every build covers every claim: links cross policies, so a claim in scope can be related to any other claim.
A requested scope (claim IDs, or a processing run) is recorded on the build.
"""

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import EdgeStrength, EventType
from app.core.logging import get_logger
from app.db.models import (
    Alert,
    Claim,
    Document,
    DuplicateMatch,
    GraphBuild,
    GraphEdge,
    GraphNode,
    LineItem,
    RelationshipGroup,
)
from app.events import event, write_events
from app.graph import edges as rules
from app.graph.alerts import CROSS_CATEGORIES, cross_claim_alerts
from app.graph.edges import ClaimInfo, DocInfo, GraphInputs, LineInfo, MatchInfo, claim_links
from app.graph.groups import MIN_WEAK_LINKS, build_groups
from app.graph.nodes import build_nodes, node_id

log = get_logger(__name__)
CHUNK = 5000
CONFIG = {
    "weak_window_days": rules.WEAK_WINDOW_DAYS,
    "amount_window_days": rules.AMOUNT_WINDOW_DAYS,
    "amount_tolerance": str(rules.AMOUNT_TOLERANCE),
    "phash_max_distance": rules.PHASH_MAX_DISTANCE,
    "min_weak_links": MIN_WEAK_LINKS,
}


async def load_inputs(session: AsyncSession) -> GraphInputs:
    claims = [
        ClaimInfo(*row)
        for row in await session.execute(
            select(
                Claim.claim_id,
                Claim.policy_number,
                Claim.claimant_id,
                Claim.claimant_name,
                Claim.incident_date,
                Claim.submission_date,
                Claim.claim_type,
                Claim.requested_amount,
                Claim.incident_reference,
                Claim.incident_reference_norm,
                Claim.status,
            ).order_by(Claim.claim_id)
        )
    ]
    lines = [
        LineInfo(*row)
        for row in await session.execute(
            select(
                LineItem.line_id,
                LineItem.claim_id,
                LineItem.invoice_reference,
                LineItem.invoice_reference_norm,
                LineItem.provider_id,
                LineItem.provider_name,
                LineItem.service_date,
                LineItem.service_code,
                LineItem.line_amount,
            ).order_by(LineItem.line_id)
        )
    ]
    documents = [
        DocInfo(*row)
        for row in await session.execute(
            select(Document.id, Document.claim_id, Document.file_name, Document.sha256, Document.phash)
            .where(Document.claim_id.is_not(None))
            .order_by(Document.id)
        )
    ]
    matches = [
        MatchInfo(*row)
        for row in await session.execute(
            select(
                DuplicateMatch.claim_id,
                DuplicateMatch.matched_claim_id,
                DuplicateMatch.match_type,
                DuplicateMatch.decision,
                DuplicateMatch.score,
            ).order_by(DuplicateMatch.id)
        )
    ]
    return GraphInputs(claims, lines, documents, matches)


async def _insert(session: AsyncSession, table: Any, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), CHUNK):
        await session.execute(insert(table), rows[start : start + CHUNK])


async def _upsert_nodes(session: AsyncSession, nodes: list[dict[str, Any]]) -> None:
    for start in range(0, len(nodes), CHUNK):
        statement = pg_insert(GraphNode.__table__).values(nodes[start : start + CHUNK])
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["node_id"],
                set_={"label": statement.excluded.label, "attributes": statement.excluded.attributes},
            )
        )


async def latest_build_id(session: AsyncSession) -> int | None:
    return await session.scalar(select(func.max(GraphBuild.build_id)).where(GraphBuild.finished_at.is_not(None)))


async def build_graph(
    session: AsyncSession, settings: Settings, claim_ids: list[str] | None = None, run_id: int | None = None
) -> GraphBuild:
    """Run one build in the caller's transaction (the caller commits)."""
    started = time.monotonic()
    scope: dict[str, Any] = {"claim_ids": claim_ids} if claim_ids else {"all": True}
    if run_id is not None:
        scope["run_id"] = run_id
    build = GraphBuild(scope=scope, config=CONFIG, run_id=run_id)
    session.add(build)
    await session.flush()

    data = await load_inputs(session)
    nodes, structural = build_nodes(data)
    links = claim_links(data)
    claims = {c.claim_id: c for c in data.claims}
    groups = build_groups(claims, links)

    await _upsert_nodes(
        session,
        [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "node_key": n.node_key,
                "label": n.label,
                "attributes": n.attributes,
            }
            for n in nodes.values()
        ],
    )
    edge_rows = [
        {
            "build_id": build.build_id,
            "from_node": node_id("claim", s.claim_id),
            "to_node": s.to_node,
            "edge_type": s.edge_type,
            "strength": EdgeStrength.STRUCTURAL.value,
            "evidence": s.evidence,
            "score": None,
        }
        for s in structural
    ]
    edge_rows += [
        {
            "build_id": build.build_id,
            "from_node": node_id("claim", link.a),
            "to_node": node_id("claim", link.b),
            "edge_type": link.link_type,
            "strength": link.strength,
            "evidence": link.evidence,
            "score": link.score,
        }
        for link in links
    ]
    await _insert(session, GraphEdge.__table__, edge_rows)

    # A group gets a new version only when its content changed; unchanged groups keep their ID and version.
    latest: dict[str, tuple[int, str]] = {}
    for gid, version, content_hash in await session.execute(
        select(RelationshipGroup.group_id, RelationshipGroup.version, RelationshipGroup.content_hash).order_by(
            RelationshipGroup.group_id, RelationshipGroup.version
        )
    ):
        latest[gid] = (version, content_hash)
    refs, new_rows, events = [], [], []
    for group in groups:
        content_hash = group.content_hash()
        version, previous = latest.get(group.group_id, (0, None))
        if previous != content_hash:
            version += 1
            new_rows.append(
                {
                    "group_id": group.group_id,
                    "version": version,
                    "build_id": build.build_id,
                    "claim_ids": group.claim_ids,
                    "policy_count": group.policy_count,
                    "tags": group.tags,
                    "total_requested": group.total_requested,
                    "summary": group.summary,
                    "content_hash": content_hash,
                }
            )
            events += [
                event(
                    EventType.GROUP_CREATED,
                    "relationship_group",
                    group.group_id,
                    claim_id=cid,
                    version=version,
                    tags=group.tags,
                    claim_ids=group.claim_ids,
                )
                for cid in group.claim_ids
            ]
        refs.append({"group_id": group.group_id, "version": version})
    await _insert(session, RelationshipGroup.__table__, new_rows)

    versions = {r["group_id"]: r["version"] for r in refs}
    alerts = cross_claim_alerts(build.build_id, groups, data, settings)
    for alert in alerts:
        alert["supporting"]["group_version"] = versions[alert["supporting"]["group_id"]]
    await session.execute(delete(Alert).where(Alert.category.in_(CROSS_CATEGORIES)))
    await _insert(session, Alert.__table__, alerts)
    events += [
        event(
            EventType.CROSS_CLAIM_ALERT_RAISED,
            "alert",
            a["finding_id"],
            claim_id=a["claim_id"],
            category=a["category"],
            group_id=a["supporting"]["group_id"],
            amount=None if a["amount"] is None else str(a["amount"]),
        )
        for a in alerts
    ]

    build.node_count = len(nodes)
    build.edge_count = len(edge_rows)
    build.group_count = len(groups)
    build.groups = refs
    build.finished_at = datetime.now(UTC)
    seconds = round(time.monotonic() - started, 2)
    events.append(
        event(
            EventType.GRAPH_BUILT,
            "graph_build",
            build.build_id,
            nodes=len(nodes),
            edges=len(edge_rows),
            groups=len(groups),
            new_group_versions=len(new_rows),
            alerts=len(alerts),
            seconds=seconds,
        )
    )
    await write_events(session, events)
    await session.flush()
    log.info(
        "graph_built",
        build_id=build.build_id,
        nodes=len(nodes),
        edges=len(edge_rows),
        groups=len(groups),
        seconds=seconds,
    )
    return build
