"""Sample invoice documents: deterministic, readable, totals match their line items, duplicate is detectable."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from scripts.datagen.render import plain_amount
from scripts.generate_data import build
from scripts.generate_invoices import DEFAULT_OUT, generate, money


@pytest.fixture(scope="module")
def invoices(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("invoices")
    generate(out, seed=42)
    return out


def files(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def test_same_seed_produces_identical_documents(invoices: Path, tmp_path: Path) -> None:
    generate(tmp_path, seed=42)
    assert files(invoices) == files(tmp_path)


def test_the_planned_documents_exist(invoices: Path) -> None:
    manifest = json.loads((invoices / "manifest.json").read_text())
    names = sorted(manifest)
    assert sorted(p.name for p in invoices.iterdir() if p.name != "manifest.json") == names
    pdfs = [n for n in names if n.endswith(".pdf")]
    assert len(pdfs) == 11 and len([n for n in pdfs if manifest[n]["duplicate_of_claim_id"]]) == 1
    assert {manifest[n]["layout"] for n in pdfs} == {"A", "B"}
    assert sorted(n for n in names if not n.endswith(".pdf")) == ["scan_01.png", "scan_02.jpg"]


def test_pdfs_open_and_print_their_reference_and_total(invoices: Path) -> None:
    manifest = json.loads((invoices / "manifest.json").read_text())
    for name, entry in manifest.items():
        if not name.endswith(".pdf"):
            continue
        data = (invoices / name).read_bytes()
        assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
        assert entry["invoice_reference"].encode() in data
        assert money(Decimal(entry["total"])).encode() in data


def test_scans_are_rotated_noisy_images(invoices: Path) -> None:
    for name, fmt in (("scan_01.png", "PNG"), ("scan_02.jpg", "JPEG")):
        with Image.open(invoices / name) as image:
            assert image.format == fmt
            assert image.size != (1240, 1754)  # rotation with expand changes the canvas
            assert sum(1 for count in image.convert("L").histogram() if count) > 20


def test_totals_match_line_items(invoices: Path) -> None:
    manifest = json.loads((invoices / "manifest.json").read_text())
    for entry in manifest.values():
        total = Decimal(0)
        for line in entry["line_items"]:
            assert Decimal(line["quantity"]) * Decimal(line["unit_price"]) == Decimal(line["amount"])
            total += Decimal(line["amount"])
        assert total == Decimal(entry["total"])


def test_documents_relate_to_the_demo_pack(invoices: Path) -> None:
    manifest = json.loads((invoices / "manifest.json").read_text())
    _, rows, _ = build(42, 1.0, demo=True)
    claims = {r["claim_id"]: r for r in rows["claims"]}
    members = {m for p in rows["policies"] for m in p["insured_member_ids"]}
    for entry in manifest.values():
        assert entry["claim_id"] not in claims
        assert entry["claimant_id"] in members
        duplicate_of = entry["duplicate_of_claim_id"]
        if duplicate_of is None:
            continue
        original = [r for r in rows["line_items"] if r["claim_id"] == duplicate_of]
        assert {r["invoice_reference"] for r in original} == {entry["invoice_reference"]}
        assert sorted(plain_amount(Decimal(x["amount"])) for x in entry["line_items"]) == sorted(
            plain_amount(Decimal(str(r["line_amount"]).replace("₹", "").replace(",", ""))) for r in original
        )
        assert entry["expected_findings"] == [
            {
                "category": "EXACT_DUPLICATE_CLAIM",
                "check_code": None,
                "match_type": "exact_claim",
                "expected_amount": entry["total"],
                "policy_rule_id": None,
                "matched_claim_id": duplicate_of,
                "service_code": None,
            }
        ]
    planted = sorted(
        f["category"] for e in manifest.values() if not e["duplicate_of_claim_id"] for f in e["expected_findings"]
    )
    assert planted == ["EXCLUDED_SERVICE", "SUB_LIMIT_EXCEEDED"]


def test_committed_invoices_are_current(invoices: Path) -> None:
    if not (DEFAULT_OUT / "manifest.json").exists():
        pytest.skip("data/sample/invoices has not been generated")
    assert files(DEFAULT_OUT) == files(invoices)
