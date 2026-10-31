"""The integration contract: one investigation bundle per claim, the evidence export with every version and event,
the machine-generated history, and a published OpenAPI file."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_corrections import corrected, key  # noqa: F401 - the fixture is used by name

REPO = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    not (REPO / "data" / "sample" / "demo" / "answer_key.json").exists(), reason="run make generate first"
)


def test_the_bundle_has_everything_the_workspace_needs(corrected: TestClient) -> None:  # noqa: F811
    showcase = key()["investigation"]["showcase"]
    body = corrected.get(f"/api/v1/claims/{showcase['claim_id']}/investigation").json()
    assert body["claim"]["claim_id"] == showcase["claim_id"] and body["lines"]
    assert body["policy"]["policy_number"] and body["policy"]["rules"]
    assert body["validation_results"] and body["alerts"]
    assert all(a["finding_id"].startswith("ALR-") for a in body["alerts"])
    assert {d["doc_type"] for d in body["documents"]} == {"invoice", "discharge_summary"}
    assert all(d["latest_extraction"]["fields"] for d in body["documents"])
    assert all(
        d["discrepancy_id"].startswith("DSC-")
        for c in body["document_comparison"]["comparisons"]
        for d in c["discrepancies"]
    )
    assert all(c["correction_id"].startswith("COR-") for c in body["corrections"]["corrections"])
    assert body["related"]["claim_id"] == showcase["claim_id"]
    summary = body["leakage"]
    assert Decimal(summary["recommended_payable"]) == Decimal(showcase["recommended_payable"])
    # Leakage is what the corrections take off beyond normal policy application (deductible and co-pay).
    beyond_policy = sum(
        Decimal(c["amount"])
        for c in showcase["expected_corrections"]
        if c["type"] not in ("APPLY_DEDUCTIBLE", "APPLY_COPAY")
    )
    assert Decimal(summary["calculated"]) == beyond_policy
    assert Decimal(summary["estimated"]) >= 0 and Decimal(summary["recovery"]) == 0


def test_finding_ids_have_type_prefixes_and_versions(corrected: TestClient) -> None:  # noqa: F811
    rel = key()["investigation"]["relationships"][0]
    body = corrected.get(f"/api/v1/claims/{rel['claim_ids'][0]}/investigation").json()
    groups = body["related"]["groups"]
    assert groups and all(g["group_id"].startswith("REL-") and g["version"] >= 1 for g in groups)
    finding_ids = body["finding_ids"]
    assert all(
        f["finding_id"][:4] in ("ALR-", "DSC-", "REL-", "COR-") and f["finding_version"] >= 1 for f in finding_ids
    )
    assert {f["finding_id"] for f in finding_ids} >= {g["group_id"] for g in groups}


def test_evidence_export_has_every_version_and_event(corrected: TestClient) -> None:  # noqa: F811
    claim_id = key()["investigation"]["showcase"]["claim_id"]
    corrected.post(f"/api/v1/claims/{claim_id}/corrections/recompute")
    export = corrected.get(f"/api/v1/claims/{claim_id}/evidence.json")
    assert export.status_code == 200
    assert "attachment" in export.headers.get("content-disposition", "")
    body = export.json()
    assert body["bundle"]["claim"]["claim_id"] == claim_id
    assert [s["version"] for s in body["correction_sets"]] == sorted(s["version"] for s in body["correction_sets"])
    assert all(s["corrections"] for s in body["correction_sets"])
    assert body["extractions"] and all(e["fields"] for e in body["extractions"])
    assert body["document_comparisons"]
    types = {e["event_type"] for e in body["events"]}
    assert {"extraction_created", "comparison_created", "correction_set_created"} <= types
    assert all(e["claim_id"] == claim_id for e in body["events"])


def test_events_are_the_claims_machine_generated_history(corrected: TestClient) -> None:  # noqa: F811
    claim_id = key()["investigation"]["showcase"]["claim_id"]
    events = corrected.get(f"/api/v1/claims/{claim_id}/events").json()
    assert events == sorted(events, key=lambda e: (e["created_at"], e["event_id"]))
    ai = [e for e in events if e["actor_type"] == "ai"]
    assert ai and all(e["model"] and e["prompt_version"] for e in ai)


def test_the_published_openapi_file_is_current(corrected: TestClient) -> None:  # noqa: F811
    committed = json.loads((REPO / "docs" / "openapi.json").read_text())
    assert committed == corrected.app.openapi(), "run `make openapi` to refresh docs/openapi.json"
    assert "InvestigationBundle" in committed["components"]["schemas"]
