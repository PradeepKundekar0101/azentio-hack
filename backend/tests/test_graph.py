"""Cross-claim correlation graph: link rules on small hand-made data, then acceptance against the sample answer keys
(every planted relationship in the right group with the right tags, no group from the controls, evidence on every
edge, stable group IDs, a full build within 30 seconds)."""

import hashlib
import json
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.documents.phash import NEAR_IDENTICAL_DISTANCE, phash, phash_distance
from app.duplicates.normalise import normalise_reference
from app.graph.edges import ClaimInfo, DocInfo, GraphInputs, LineInfo, MatchInfo, claim_links
from app.graph.groups import build_groups, group_id
from scripts.seed_reference import seed_reference
from tests.test_answer_key import all_pages, import_and_run
from tests.test_imports_api import MemoryStorage

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample"
D = date(2026, 3, 10)

pytestmark = pytest.mark.skipif(not (SAMPLE / "answer_key.json").exists(), reason="run make generate first")


# ---- link rules on hand-made data --------------------------------------------------------------------------------


def claim(cid: str, policy: str, claimant: str, requested: str = "10000", incident: date = D, **kw) -> ClaimInfo:
    values = {
        "claim_id": cid,
        "policy_number": policy,
        "claimant_id": claimant,
        "claimant_name": f"Name {claimant}",
        "incident_date": incident,
        "submission_date": incident,
        "claim_type": "outpatient",
        "requested_amount": Decimal(requested),
        "incident_reference": None,
        "incident_reference_norm": None,
        "status": "open",
    }
    values.update(kw)
    return ClaimInfo(**values)


def line(lid: str, cid: str, ref: str, provider: str = "PRV-0001", day: date = D, amount: str = "10000") -> LineInfo:
    return LineInfo(
        lid, cid, ref, normalise_reference(ref) or "", provider, f"Hospital {provider}", day, "DX-CT", Decimal(amount)
    )


def inputs(claims, lines, documents=(), matches=()) -> GraphInputs:
    return GraphInputs(list(claims), list(lines), list(documents), list(matches))


def strong(links: list) -> list:
    return [x for x in links if x.strength == "strong"]


def test_shared_invoice_across_policies_is_a_strong_link_with_evidence() -> None:
    data = inputs(
        [claim("C1", "P1", "M1"), claim("C2", "P2", "M2")],
        [line("L1", "C1", "INV-452"), line("L2", "C2", "inv 452")],
    )
    (link,) = strong(claim_links(data))
    assert (link.a, link.b, link.link_type, link.strength) == ("C1", "C2", "shared_invoice", "strong")
    assert link.tag == "INVOICE_REUSED_ACROSS_POLICIES"
    assert link.evidence["fields"] == ["provider_id", "invoice_reference"]
    assert link.evidence["values"]["invoice_reference"] == {"C1": "INV-452", "C2": "inv 452"}
    assert link.evidence["values"]["provider_id"] == "PRV-0001"


def test_shared_incident_reference_across_policies() -> None:
    data = inputs(
        [
            claim("C1", "P1", "M1", incident_reference="ADM-000881", incident_reference_norm="ADM881"),
            claim("C2", "P2", "M9", incident_reference="adm 881", incident_reference_norm="ADM881"),
        ],
        [line("L1", "C1", "INV-1"), line("L2", "C2", "INV-2")],
    )
    (link,) = strong(claim_links(data))
    assert (link.link_type, link.tag) == ("shared_incident", "INCIDENT_CLAIMED_TWICE")
    assert link.evidence["values"]["incident_reference"] == {"C1": "ADM-000881", "C2": "adm 881"}


def test_busy_provider_and_shared_policy_alone_never_link_claims() -> None:
    claims = [claim(f"C{k}", "P1" if k < 4 else f"P{k}", f"M{k}", requested=str(10000 + k * 900)) for k in range(30)]
    lines = [line(f"L{k}", f"C{k}", f"INV-{k}", day=date(2026, 3, 1 + k % 28)) for k in range(30)]
    assert claim_links(inputs(claims, lines)) == [] or all(
        link.strength == "weak" for link in claim_links(inputs(claims, lines))
    )
    groups = build_groups({c.claim_id: c for c in claims}, claim_links(inputs(claims, lines)))
    assert groups == []


def test_two_weak_links_relate_a_pair_but_one_does_not() -> None:
    # Same policy and provider within 7 days (different claimants), and amounts within 2%: two weak links.
    claims = [claim("C1", "P1", "M1", "20000"), claim("C2", "P1", "M2", "20200", incident=date(2026, 3, 13))]
    lines = [
        line("L1", "C1", "INV-1", amount="20000"),
        line("L2", "C2", "INV-2", day=date(2026, 3, 13), amount="20200"),
    ]
    links = claim_links(inputs(claims, lines))
    assert sorted(link.link_type for link in links) == ["same_policy_provider", "similar_amount"]
    (group,) = build_groups({c.claim_id: c for c in claims}, links)
    assert group.tags == ["WEAK_PATTERN"]
    # Only the amount link: no group.
    claims[1] = claim("C2", "P7", "M2", "20200", incident=date(2026, 3, 13))
    assert build_groups({c.claim_id: c for c in claims}, claim_links(inputs(claims, lines))) == []


def test_cleared_repeats_never_link() -> None:
    claims = [claim("C1", "P1", "M1", "1500"), claim("C2", "P1", "M1", "1500", incident=date(2026, 3, 14))]
    lines = [line("L1", "C1", "INV-1", amount="1500"), line("L2", "C2", "INV-2", day=date(2026, 3, 14), amount="1500")]
    cleared = [MatchInfo("C2", "C1", "legitimate_repeat", "cleared", None)]
    assert claim_links(inputs(claims, lines, matches=cleared)) == []


def test_concurrent_stays_need_different_providers_and_overlapping_dates() -> None:
    claims = [
        claim("C1", "P1", "M1", claim_type="inpatient"),
        claim("C2", "P1", "M1", claim_type="inpatient", incident=date(2026, 3, 12)),
    ]
    lines = [
        line("L1", "C1", "INV-1", "PRV-0001", date(2026, 3, 10)),
        line("L2", "C1", "INV-1", "PRV-0001", date(2026, 3, 14)),
        line("L3", "C2", "INV-2", "PRV-0002", date(2026, 3, 12)),
        line("L4", "C2", "INV-2", "PRV-0002", date(2026, 3, 15)),
    ]
    (link,) = strong(claim_links(inputs(claims, lines)))
    assert (link.link_type, link.tag) == ("overlapping_stays", "CONCURRENT_STAYS")
    assert link.evidence["values"]["periods"] == {
        "C1": ["2026-03-10", "2026-03-14"],
        "C2": ["2026-03-12", "2026-03-15"],
    }


def test_reused_documents_by_hash_or_near_identical_image() -> None:
    claims = [claim("C1", "P1", "M1"), claim("C2", "P2", "M2"), claim("C3", "P3", "M3")]
    lines = [line("L1", "C1", "INV-1"), line("L2", "C2", "INV-2"), line("L3", "C3", "INV-3")]
    docs = [
        DocInfo(1, "C1", "a.png", "f" * 64, "f" * 64),
        DocInfo(2, "C2", "b.png", "e" * 64, "f" * 63 + "0"),  # 4 bits apart
        DocInfo(3, "C3", "c.pdf", "d" * 64, None),
    ]
    links = claim_links(inputs(claims, lines, documents=docs))
    (link,) = [x for x in links if x.link_type == "shared_document"]
    assert (link.a, link.b, link.tag) == ("C1", "C2", "DOCUMENT_REUSED")
    assert link.evidence["values"]["hash_distance"] == 4


def test_different_bills_on_one_template_are_not_near_identical() -> None:
    scans = [SAMPLE / "invoices" / "scan_01.png", SAMPLE / "invoices" / "scan_02.jpg"]
    hashes = []
    for path in scans:
        with Image.open(path) as image:
            hashes.append(phash(image))
    assert phash_distance(*hashes) > NEAR_IDENTICAL_DISTANCE


def test_group_ids_derive_from_sorted_members() -> None:
    assert group_id(["C2", "C1"]) == group_id(["C1", "C2"]) != group_id(["C1", "C3"])
    assert group_id(["C1", "C2"]).startswith("REL-")


# ---- acceptance against the sample answer keys --------------------------------------------------------------------


@pytest.fixture
def api(settings: Settings, auth_client: TestClient) -> TestClient:
    seed_reference(settings)
    auth_client.app.state.storage = MemoryStorage()
    return auth_client


def attach_documents(sql, root: Path) -> None:
    """Attach the demo pack's supporting documents to their claims, as uploads would."""
    key = json.loads((root / "answer_key.json").read_text())
    for doc in key["investigation"]["documents"]:
        path = root / "documents" / doc["file"]
        data = path.read_bytes()
        image_hash = None
        if path.suffix == ".png":
            with Image.open(path) as image:
                image_hash = phash(image)
        sql(
            "insert into documents (claim_id, storage_key, sha256, file_name, file_type, size_bytes, parse_status,"
            " phash)"
            " values (:c, :k, :s, :f, :t, :n, 'pending', :p)",
            c=doc["claim_id"],
            k=f"test/{doc['file']}",
            s=hashlib.sha256(data).hexdigest(),
            f=doc["file"],
            t=path.suffix[1:],
            n=len(data),
            p=image_hash,
        )


def expected_level_one_pairs(key: dict) -> set[frozenset[str]]:
    """Claim pairs the base duplicate checks connect (exact and near duplicates, lines repeated across claims)."""
    pairs = set()
    for f in key["findings"]:
        if f["matched_claim_id"] and f["scenario"] not in ("invoice_reused_across_policies", "chain"):
            pairs.add(frozenset((f["claim_id"], f["matched_claim_id"])))
    return pairs


def check_groups(api: TestClient, key: dict) -> list[dict]:
    groups = all_pages(api, "/api/v1/relationship-groups")
    by_members = {tuple(g["claim_ids"]): g for g in groups}
    for rel in key["investigation"]["relationships"]:
        group = by_members.get(tuple(rel["claim_ids"]))
        assert group is not None, rel
        assert sorted(group["tags"]) == rel["tags"], (rel, group)
    # Every other group comes from the base duplicate findings: no group from busy providers, family policies or
    # cleared repeats.
    planted = {tuple(rel["claim_ids"]) for rel in key["investigation"]["relationships"]}
    explained = expected_level_one_pairs(key)
    for group in groups:
        if tuple(group["claim_ids"]) in planted:
            continue
        members = set(group["claim_ids"])
        assert any(pair <= members for pair in explained), group
        assert "WEAK_PATTERN" not in group["tags"], group
    return groups


def test_demo_pack_relationships_are_found(api: TestClient, sql) -> None:
    root = SAMPLE / "demo"
    key = json.loads((root / "answer_key.json").read_text())
    import_and_run(api, root, "csv")
    attach_documents(sql, root)
    build = api.post("/api/v1/graph/rebuild", json={}).json()
    assert build["group_count"] >= len(key["investigation"]["relationships"])
    groups = check_groups(api, key)

    # Every edge has evidence naming the matched fields and their values; no edge comes from the LLM.
    for group in groups:
        detail = api.get(f"/api/v1/relationship-groups/{group['group_id']}").json()
        assert {m["claim_id"] for m in detail["members"]} == set(group["claim_ids"])
        assert detail["edges"]
        for edge in detail["edges"]:
            assert edge["evidence"]["fields"], edge
            assert all(field in edge["evidence"]["values"] for field in edge["evidence"]["fields"]), edge
            assert edge["generated_by"] == "rule"

    # The claim view: its groups and the subgraph, with hubs shown but not expanded.
    rel = next(r for r in key["investigation"]["relationships"] if r["scenario"] == "invoice_reused_across_policies")
    related = api.get(f"/api/v1/claims/{rel['claim_ids'][0]}/related").json()
    assert [g["claim_ids"] for g in related["groups"]] == [rel["claim_ids"]]
    node_ids = {n["node_id"] for n in related["nodes"]}
    assert {f"claim:{cid}" for cid in rel["claim_ids"]} <= node_ids
    hubs = [n for n in related["nodes"] if n["node_type"] in ("provider", "policy")]
    assert hubs and all(n["expanded"] is False for n in hubs)
    invoice = next(n for n in related["nodes"] if n["node_type"] == "invoice")
    records = api.get(f"/api/v1/graph/nodes/{invoice['node_id']}/records").json()
    assert {c["claim_id"] for c in records["claims"]} == set(rel["claim_ids"])
    assert records["lines"]

    # Cross-claim alerts on the later claim of each relationship.
    alerts = sql(
        "select claim_id, category, amount_type, amount, supporting from alerts where category in "
        "('CROSS_POLICY_INVOICE_REUSE', 'INCIDENT_CLAIMED_TWICE', 'CONCURRENT_STAYS', 'DOCUMENT_REUSED')"
    )
    categories = {(a[0], a[1]): a for a in alerts}
    expected = {
        "invoice_reused_across_policies": ("CROSS_POLICY_INVOICE_REUSE", "calculated"),
        "incident_claimed_twice": ("INCIDENT_CLAIMED_TWICE", "estimated"),
        "concurrent_stays": ("CONCURRENT_STAYS", "suspected"),
        "document_reused": ("DOCUMENT_REUSED", "calculated"),
    }
    for rel in key["investigation"]["relationships"]:
        if rel["scenario"] not in expected:
            continue
        category, amount_type = expected[rel["scenario"]]
        matches = [a for (cid, cat), a in categories.items() if cat == category and cid in rel["claim_ids"]]
        assert len(matches) == 1, (rel, matches)
        alert = matches[0]
        assert alert[2] == amount_type
        assert (alert[3] is None) == (amount_type == "suspected")
        assert alert[4]["group_id"] == group_id(rel["claim_ids"])
        assert alert[4]["edges"] and alert[4]["matched_claim_ids"]


def test_rebuilding_without_changes_keeps_group_ids_and_versions(api: TestClient, sql) -> None:
    root = SAMPLE / "demo"
    import_and_run(api, root, "csv")
    first = {(g["group_id"], g["version"]) for g in all_pages(api, "/api/v1/relationship-groups")}
    api.post("/api/v1/graph/rebuild", json={})
    second = {(g["group_id"], g["version"]) for g in all_pages(api, "/api/v1/relationship-groups")}
    assert first == second and first
    assert sql("select count(*) from graph_builds")[0][0] == 2
    events = {r[0] for r in sql("select distinct event_type from analysis_events")}
    assert {"graph_built", "group_created", "cross_claim_alert_raised"} <= events


def test_full_sample_relationships_within_time(api: TestClient, sql) -> None:
    key = json.loads((SAMPLE / "answer_key.json").read_text())
    import_and_run(api, SAMPLE, "csv")
    started = time.monotonic()
    build = api.post("/api/v1/graph/rebuild", json={}).json()
    assert time.monotonic() - started < 30
    assert build["edge_count"] > 0
    check_groups(api, key)
