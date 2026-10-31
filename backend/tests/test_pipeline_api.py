from decimal import Decimal

from fastapi.testclient import TestClient

from tests.ingest_fixtures import BASE, to_csv_files
from tests.test_imports_api import api, upload  # noqa: F401 - fixture reuse


def test_run_validates_claims_and_raises_the_overpayment(api: TestClient) -> None:  # noqa: F811
    batch = upload(api, to_csv_files(BASE)).json()

    started = api.post("/api/v1/runs", json={"scope": "batch", "batch_id": batch["id"]})
    run = api.get(f"/api/v1/runs/{started.json()['id']}").json()
    claim = api.get("/api/v1/claims/CLM-000001").json()
    open_claim = api.get("/api/v1/claims/CLM-000002").json()

    assert started.status_code == 202
    assert run["status"] == "completed", run
    assert run["claims_processed"] == 2
    c06 = next(r for r in claim["results"] if r["check_code"] == "C06" and r["outcome"] == "fail")
    assert Decimal(c06["amount_impact"]) == Decimal("6000")
    assert [s["step_code"] for s in claim["payable_steps"]][-1] == "C11 OVERALL_LIMIT"
    assert Decimal(claim["claim"]["payable"]) == Decimal("10800")
    assert [(a["category"], Decimal(a["amount"])) for a in claim["alerts"]] == [
        ("SETTLEMENT_OVERPAYMENT", Decimal("4500"))
    ]
    assert open_claim["alerts"] == []
    assert {r["outcome"] for r in open_claim["results"]} <= {"pass", "adjusted", "not_applicable"}
    assert claim["policy"]["rules"][0]["rule_id"] == "POL-000001-CV-01"
    assert claim["lines"][0]["source_row"]["row_number"] == 2


def test_rerunning_replaces_results(api: TestClient, sql) -> None:  # noqa: F811
    upload(api, to_csv_files(BASE))

    api.post("/api/v1/runs", json={"scope": "all"})
    first = sql("select count(*) from validation_results")[0][0]
    api.post("/api/v1/runs", json={"scope": "all"})

    assert sql("select count(*) from validation_results")[0][0] == first
    assert sql("select count(distinct run_id) from validation_results")[0][0] == 1
    assert api.get("/api/v1/runs/latest").json()["scope"] == "all"


def test_batch_scope_requires_an_existing_batch(api: TestClient) -> None:  # noqa: F811
    assert api.post("/api/v1/runs", json={"scope": "batch"}).status_code == 422
    assert api.post("/api/v1/runs", json={"scope": "batch", "batch_id": 999}).status_code == 404


def test_alerts_and_dashboard_agree_and_filter(api: TestClient) -> None:  # noqa: F811
    batch = upload(api, to_csv_files(BASE)).json()
    api.post("/api/v1/runs", json={"scope": "batch", "batch_id": batch["id"]})

    alerts = api.get("/api/v1/alerts").json()
    summary = api.get("/api/v1/dashboard/summary").json()
    none = api.get("/api/v1/alerts", params={"claim_type": "outpatient"}).json()
    by_provider = api.get("/api/v1/dashboard/summary", params={"provider_id": "PRV-0002"}).json()

    assert alerts["total"] == 1
    row = alerts["items"][0]
    assert row["claimant"] == "R*** K***"
    assert row["provider_id"] == "PRV-0001"
    assert summary["kpis"]["claims_processed"] == 2
    assert summary["kpis"]["flagged_claims"] == 1
    assert Decimal(summary["kpis"]["calculated_leakage"]) == Decimal("4500")
    assert summary["top_providers"][0]["provider_id"] == "PRV-0001"
    assert summary["last_run"]["status"] == "completed"
    assert none["total"] == 0
    assert by_provider["kpis"]["flagged_claims"] == 0 and by_provider["kpis"]["claims_processed"] == 1

    detail = api.get(f"/api/v1/alerts/{row['id']}").json()
    assert detail["claim"]["claim"]["claimant_name"] == "Ravi Kumar"
    assert detail["alert"]["supporting"]["settlement_id"] == "STL-0000001"

    patched = api.patch(f"/api/v1/alerts/{row['id']}", json={"status": "reviewed", "note": "Recovered"}).json()
    assert patched["status"] == "reviewed" and patched["review_note"] == "Recovered"
    assert api.get("/api/v1/dashboard/summary").json()["kpis"]["open_alerts"] == 0
    assert api.get("/api/v1/duplicates/cleared").json() == {"items": [], "total": 0}


def test_claims_list_shows_clean_and_flagged_open_claims(api: TestClient) -> None:  # noqa: F811
    batch = upload(api, to_csv_files(BASE)).json()
    before = api.get("/api/v1/claims").json()
    api.post("/api/v1/runs", json={"scope": "batch", "batch_id": batch["id"]})

    open_claims = api.get("/api/v1/claims").json()
    settled = api.get("/api/v1/claims", params={"status": "settled"}).json()
    clean = api.get("/api/v1/claims", params={"status": "all", "review": "clean"}).json()
    search = api.get("/api/v1/claims", params={"status": "all", "q": "clm-000001"}).json()

    assert before["items"][0]["review"] == "not_validated"
    assert [(c["claim_id"], c["review"]) for c in open_claims["items"]] == [("CLM-000002", "clean")]
    row = open_claims["items"][0]
    assert row["claimant"] == "A*** K***" and Decimal(row["payable"]) == Decimal("14400")
    assert settled["items"][0]["review"] == "flagged"
    assert settled["items"][0]["top_severity"] == "high"
    assert Decimal(settled["items"][0]["calculated_leakage"]) == Decimal("4500")
    assert [c["claim_id"] for c in clean["items"]] == ["CLM-000002"]
    assert search["total"] == 1
