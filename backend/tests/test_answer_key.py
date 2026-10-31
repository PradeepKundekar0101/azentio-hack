"""Acceptance against the generated answer key: import the sample, process it, and compare every finding."""

import json
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from scripts.seed_reference import seed_reference
from tests.test_imports_api import MemoryStorage

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample"
DATASETS = ("policies", "policy_rules", "claims", "line_items", "settlements")

pytestmark = pytest.mark.skipif(not (SAMPLE / "answer_key.json").exists(), reason="run make generate first")


def files(root: Path, fmt: str) -> list[tuple[str, bytes]]:
    if fmt == "csv":
        return [(f"{name}.csv", (root / "csv" / f"{name}.csv").read_bytes()) for name in DATASETS]
    if fmt == "xlsx":
        return [("claims_data.xlsx", (root / "xlsx" / "claims_data.xlsx").read_bytes())]
    return [("claims_data.json", (root / "json" / "claims_data.json").read_bytes())]


@pytest.fixture
def api(settings: Settings, auth_client: TestClient) -> TestClient:
    seed_reference(settings)
    auth_client.app.state.storage = MemoryStorage()
    return auth_client


def import_and_run(api: TestClient, root: Path, fmt: str) -> dict:
    started = time.monotonic()
    batch = api.post("/api/v1/imports", files=[("files", f) for f in files(root, fmt)]).json()
    import_seconds = time.monotonic() - started
    started = time.monotonic()
    run = api.post("/api/v1/runs", json={"scope": "batch", "batch_id": batch["id"]}).json()
    run = api.get(f"/api/v1/runs/{run['id']}").json()
    return {"batch": batch, "run": run, "import_seconds": import_seconds, "run_seconds": time.monotonic() - started}


def all_pages(api: TestClient, path: str, **params) -> list[dict]:
    items, page = [], 1
    while True:
        body = api.get(path, params={**params, "page": page, "page_size": 200}).json()
        items += body["items"]
        if len(items) >= body["total"]:
            return items
        page += 1


def check_against_key(api: TestClient, sql, root: Path, outcome: dict) -> None:
    key = json.loads((root / "answer_key.json").read_text())
    batch, run = outcome["batch"], outcome["run"]
    assert batch["status"] == "completed"
    assert run["status"] == "completed", run
    assert run["claims_failed"] == 0

    # Reconciliation and accepted counts per dataset.
    for name, counts in batch["counts"].items():
        assert counts["received"] == counts["accepted"] + counts["warnings"] + counts["rejected"], name
        assert counts["accepted"] + counts["warnings"] == key["accepted_counts"][name], name

    # Every planted invalid row is rejected or warned with the expected code at the expected row.
    issues = all_pages(api, f"/api/v1/imports/{batch['id']}/issues")
    found = {(i["dataset"], i["row_number"], i["code"]) for i in issues}
    offset = 1 if (root / "json").exists() and batch["files"][0]["file_name"].endswith(".json") else 2
    missing = [r for r in key["invalid_rows"] if (r["dataset"], r["row_index"] + offset, r["error_code"]) not in found]
    assert not missing, missing[:5]

    # Every planted finding has its alert with the expected amount and type, and nothing else is flagged.
    alerts = sql("select claim_id, line_id, category, amount_type, amount, policy_rule_id from alerts")
    by_claim: dict[tuple, list] = {}
    for claim_id, line_id, category, amount_type, amount, rule_id in alerts:
        by_claim.setdefault((claim_id, category), []).append((line_id, amount_type, amount, rule_id))
    misses = []
    for finding in key["findings"]:
        candidates = by_claim.get((finding["claim_id"], finding["category"]), [])
        expected = Decimal(finding["expected_amount"])
        ok = [
            c
            for c in candidates
            if c[1] == finding["amount_type"]
            and abs(c[2] - expected) <= Decimal("1.00")
            and (
                finding.get("line_id") is None
                or c[0] in (None, finding["line_id"])
                or finding["category"] != "DUPLICATE_LINE_ITEM"
            )
        ]
        if not ok:
            misses.append((finding["scenario"], finding["claim_id"], str(expected), candidates))
    assert not misses, f"{len(misses)} findings missed, e.g. {misses[:5]}"
    planted = Counter((f["claim_id"], f["category"]) for f in key["findings"])
    extra = [(k, len(v)) for k, v in by_claim.items() if len(v) > planted.get(k, 0)]
    assert not extra, f"{len(extra)} unexpected alerts, e.g. {extra[:5]}"

    # Legitimate repeats are cleared with a reason and never alerted.
    cleared = {
        (r[0], r[1]) for r in sql("select claim_id, matched_claim_id from duplicate_matches where decision='cleared'")
    }
    for repeat in key["legitimate_repeats"]:
        assert (repeat["claim_id"], repeat["matched_claim_id"]) in cleared, repeat
        assert not any(k[0] == repeat["claim_id"] for k in by_claim), repeat


@pytest.mark.parametrize("fmt", ["csv", "xlsx", "json"])
def test_demo_pack_matches_its_answer_key(api: TestClient, sql, fmt: str) -> None:
    outcome = import_and_run(api, SAMPLE / "demo", fmt)
    check_against_key(api, sql, SAMPLE / "demo", outcome)


def test_full_sample_matches_the_answer_key_within_time(api: TestClient, sql) -> None:
    outcome = import_and_run(api, SAMPLE, "csv")

    check_against_key(api, sql, SAMPLE, outcome)
    assert outcome["import_seconds"] < 30, outcome["import_seconds"]
    assert outcome["run_seconds"] < 30, outcome["run_seconds"]
