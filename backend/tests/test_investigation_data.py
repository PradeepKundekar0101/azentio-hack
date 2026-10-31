"""Generated data for cross-claim correlation, document analysis and corrections: every scenario exists with its
stated count and an answer-key entry, documents are deterministic, and clean documents match their claims."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from app.core.money import parse_amount
from app.documents.phash import phash, phash_distance
from scripts.datagen.common import norm_ref, parse_date
from scripts.datagen.investigation import (
    BUSY_PROVIDER_CLAIMS,
    DEMO_DISCREPANCY_COUNTS,
    DEMO_RELATIONSHIP_COUNTS,
    RELATIONSHIP_COUNTS,
)
from scripts.datagen.readback import read_csv_dir
from scripts.generate_data import build, generate

SAMPLE_DEMO = Path(__file__).resolve().parents[2] / "data" / "sample" / "demo"


@pytest.fixture(scope="module")
def full() -> tuple[dict, dict]:
    _, rows, key = build(42, 1.0, demo=False)
    return rows, key


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("sample")
    generate(out, seed=42, scale=0.05)
    return out / "demo"


def claims_by_id(rows: dict) -> dict[str, dict]:
    return {r["claim_id"]: r for r in rows["claims"]}


def lines_by_claim(rows: dict) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = defaultdict(list)
    for line in rows["line_items"]:
        found[line["claim_id"]].append(line)
    return found


def day(value: str) -> date:
    parsed, _ = parse_date(value)
    assert parsed is not None, value
    return parsed


def amount(value: object) -> Decimal:
    parsed = parse_amount(str(value))
    assert parsed is not None, value
    return parsed


def check_relationship(rel: dict, claims: dict[str, dict], lines: dict[str, list[dict]]) -> None:
    members = [claims[cid] for cid in rel["claim_ids"]]
    assert rel["claim_ids"] == sorted(rel["claim_ids"])
    if rel["scenario"] == "chain":
        assert len(members) == 3
        assert set(rel["tags"]) == {"INVOICE_REUSED_ACROSS_POLICIES", "INCIDENT_CLAIMED_TWICE"}
        return
    assert len(members) == 2
    a, b = members
    if rel["scenario"] == "invoice_reused_across_policies":
        assert a["policy_number"] != b["policy_number"] and a["claimant_id"] != b["claimant_id"]
        refs = [
            {(ln["provider_id"], norm_ref(ln["invoice_reference"])) for ln in lines[c["claim_id"]]} for c in members
        ]
        assert refs[0] & refs[1]
    elif rel["scenario"] == "incident_claimed_twice":
        assert a["policy_number"] != b["policy_number"]
        assert norm_ref(a["incident_reference"]) == norm_ref(b["incident_reference"]) != ""
    elif rel["scenario"] == "concurrent_stays":
        assert a["claimant_id"] == b["claimant_id"] and a["claim_type"] == b["claim_type"] == "inpatient"
        spans = [
            (min(day(ln["service_date"]) for ln in lines[c["claim_id"]]),
             max(day(ln["service_date"]) for ln in lines[c["claim_id"]]))
            for c in members
        ]  # fmt: skip
        assert spans[0][0] <= spans[1][1] and spans[1][0] <= spans[0][1]
        providers = [{ln["provider_id"] for ln in lines[c["claim_id"]]} for c in members]
        assert not providers[0] & providers[1]
    elif rel["scenario"] == "document_reused":
        assert a["claimant_id"] != b["claimant_id"]
    else:
        raise AssertionError(rel["scenario"])


def test_full_set_has_every_relationship_with_its_count(full: tuple[dict, dict]) -> None:
    rows, key = full
    section = key["investigation"]
    counts = Counter(rel["scenario"] for rel in section["relationships"])
    assert dict(counts) == {s: n for s, n in RELATIONSHIP_COUNTS.items() if n}
    claims, lines = claims_by_id(rows), lines_by_claim(rows)
    for rel in section["relationships"]:
        check_relationship(rel, claims, lines)
    # Relationship groups never share a claim, so each planted group stays a group of its own.
    members = [cid for rel in section["relationships"] for cid in rel["claim_ids"]]
    assert len(members) == len(set(members))


def test_full_set_has_the_control_entities(full: tuple[dict, dict]) -> None:
    rows, key = full
    controls = key["investigation"]["controls"]
    lines = lines_by_claim(rows)
    busy = controls["busy_provider"]
    at_busy = {cid for cid, items in lines.items() if any(ln["provider_id"] == busy for ln in items)}
    assert len(at_busy) >= BUSY_PROVIDER_CLAIMS
    claims = claims_by_id(rows)
    family = controls["family_policy"]
    claimants = {c["claimant_id"] for c in claims.values() if c["policy_number"] == family}
    assert len(claimants) >= 4
    assert controls["cleared_repeats"] == len(key["legitimate_repeats"]) > 0


def test_findings_raised_by_the_new_claims_are_in_the_answer_key(full: tuple[dict, dict]) -> None:
    _, key = full
    reuse = [f for f in key["findings"] if f["scenario"] == "invoice_reused_across_policies"]
    assert reuse and all(f["category"] == "DUPLICATE_LINE_ITEM" for f in reuse)
    multi = {f["claim_id"] for f in key["findings"] if f["scenario"].startswith("multi_issue")}
    assert multi == {m["claim_id"] for m in key["investigation"]["multi_issue_claims"]}


def test_multi_issue_claims_reconcile(full: tuple[dict, dict]) -> None:
    rows, key = full
    claims = claims_by_id(rows)
    multi = key["investigation"]["multi_issue_claims"]
    assert len(multi) >= 3
    for item in multi:
        requested = Decimal(item["requested_amount"])
        assert requested == amount(claims[item["claim_id"]]["requested_amount"])
        types = [c["type"] for c in item["expected_corrections"]]
        assert {"REMOVE_DUPLICATE_LINE", "CAP_AT_SUB_LIMIT", "APPLY_COPAY"} <= set(types)
        total = sum((Decimal(c["amount"]) for c in item["expected_corrections"]), Decimal(0))
        assert requested - total == Decimal(item["recommended_payable"])


def test_demo_pack_has_every_relationship_with_its_count(demo: Path) -> None:
    key = json.loads((demo / "answer_key.json").read_text())
    rows = read_csv_dir(demo / "csv")
    section = key["investigation"]
    counts = Counter(rel["scenario"] for rel in section["relationships"])
    assert dict(counts) == DEMO_RELATIONSHIP_COUNTS
    claims, lines = claims_by_id(rows), lines_by_claim(rows)
    for rel in section["relationships"]:
        check_relationship(rel, claims, lines)


def document_files(demo: Path) -> dict[str, dict]:
    key = json.loads((demo / "answer_key.json").read_text())
    return {d["file"]: d for d in key["investigation"]["documents"]}


def test_demo_documents_cover_about_forty_claims(demo: Path) -> None:
    docs = document_files(demo)
    assert all((demo / "documents" / name).is_file() for name in docs)
    assert sorted(p.name for p in (demo / "documents").iterdir()) == sorted(docs)
    claims = {d["claim_id"] for d in docs.values()}
    assert 35 <= len(claims) <= 50
    kinds = Counter((d["doc_type"], d["kind"]) for d in docs.values())
    assert kinds[("invoice", "scan")] == 3
    assert kinds[("discharge_summary", "pdf")] >= 8
    assert {d["layout"] for d in docs.values() if d["doc_type"] == "invoice" and d["kind"] == "pdf"} == {"A", "B"}
    assert sum(1 for d in docs.values() if d["clean"]) >= 10


def test_demo_planted_discrepancies_have_their_counts(demo: Path) -> None:
    key = json.loads((demo / "answer_key.json").read_text())
    planted = Counter(d["scenario"] for d in key["investigation"]["document_discrepancies"] if d["planted"])
    assert dict(planted) == DEMO_DISCREPANCY_COUNTS
    rows = read_csv_dir(demo / "csv")
    line_ids = {ln["line_id"] for ln in rows["line_items"]}
    for item in key["investigation"]["document_discrepancies"]:
        assert item["file"] in document_files(demo)
        assert item["line_id"] is None or item["line_id"] in line_ids
        assert item["amount_type"] in ("calculated", "estimated", None)


def pdf_text(path: Path) -> str:
    document = pdfium.PdfDocument(path)
    try:
        return "\n".join(page.get_textpage().get_text_range() for page in document)
    finally:
        document.close()


def test_clean_documents_match_their_claims_exactly(demo: Path) -> None:
    rows = read_csv_dir(demo / "csv")
    claims, lines = claims_by_id(rows), lines_by_claim(rows)
    docs = [d for d in document_files(demo).values() if d["clean"]]
    for doc in docs:
        claim = claims[doc["claim_id"]]
        expected = doc["expected"]
        assert expected["patient_name"] == claim["claimant_name"]
        if doc["doc_type"] != "invoice":
            continue
        claimed = [
            ln
            for ln in lines[claim["claim_id"]]
            if norm_ref(ln["invoice_reference"]) == norm_ref(expected["invoice_number"])
        ]
        assert len(claimed) == len(expected["lines"])
        for ln, printed in zip(sorted(claimed, key=lambda x: x["line_id"]), expected["lines"], strict=True):
            assert printed["line_id"] == ln["line_id"]
            assert Decimal(printed["amount"]) == amount(ln["line_amount"])
        if doc["kind"] == "pdf":
            text = pdf_text(demo / "documents" / doc["file"])
            assert expected["invoice_number"] in text
            assert expected["total"].split(".")[0][-3:] in text.replace(",", "")


def test_reused_documents_are_identical_or_near_identical(demo: Path) -> None:
    docs = document_files(demo)
    reused = [d for d in docs.values() if d["reuse_of"]]
    assert len(reused) == 3
    exact = near = 0
    for doc in reused:
        original = demo / "documents" / doc["reuse_of"]
        copy = demo / "documents" / doc["file"]
        if hashlib.sha256(original.read_bytes()).digest() == hashlib.sha256(copy.read_bytes()).digest():
            exact += 1
        else:
            with Image.open(original) as a, Image.open(copy) as b:
                assert phash_distance(phash(a), phash(b)) <= 5
            near += 1
    assert (exact, near) == (2, 1)


def test_same_seed_produces_identical_documents(demo: Path, tmp_path: Path) -> None:
    generate(tmp_path, seed=42, scale=0.05)
    again = tmp_path / "demo" / "documents"
    first = {p.name: p.read_bytes() for p in (demo / "documents").iterdir()}
    assert first == {p.name: p.read_bytes() for p in again.iterdir()}


@pytest.mark.skipif(not (SAMPLE_DEMO / "answer_key.json").exists(), reason="data/sample has not been generated")
def test_committed_demo_pack_has_documents() -> None:
    assert len(document_files(SAMPLE_DEMO)) >= 40
