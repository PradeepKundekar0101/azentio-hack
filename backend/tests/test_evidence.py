import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from app.db.models import EvidenceEvent
from app.evidence.chain import verify
from tests.ingest_fixtures import BASE, to_csv_files
from tests.test_imports_api import api, upload  # noqa: F401 - fixture reuse

CLAIM = "CLM-000001"


def _processed(api: TestClient) -> dict:  # noqa: F811
    batch = upload(api, to_csv_files(BASE)).json()
    api.post("/api/v1/runs", json={"scope": "batch", "batch_id": batch["id"]})
    return api.get("/api/v1/alerts").json()["items"][0]


def test_a_claim_has_no_investigation_until_someone_acts(api: TestClient) -> None:  # noqa: F811
    _processed(api)

    view = api.get(f"/api/v1/evidence/claims/{CLAIM}").json()

    assert view["investigation"] is None
    assert view["events"] == []
    assert view["integrity"]["verified"] is True
    assert [f["category"] for f in view["findings"]] == ["SETTLEMENT_OVERPAYMENT"]
    assert api.get("/api/v1/evidence/claims/CLM-999999").status_code == 404


def test_a_decision_opens_the_investigation_with_the_original_calculation(api: TestClient) -> None:  # noqa: F811
    alert = _processed(api)

    api.patch(f"/api/v1/alerts/{alert['id']}", json={"status": "reviewed", "note": "Co-pay was missed"})
    view = api.get(f"/api/v1/evidence/claims/{CLAIM}").json()

    opened, decision = reversed(view["events"])
    assert opened["kind"] == "opened" and opened["seq"] == 1 and opened["actor"] == "demo"
    assert Decimal(opened["payload"]["totals"]["calculated_leakage"]) == Decimal("4500")
    assert opened["payload"]["payable_steps"][-1]["step_code"] == "C11 OVERALL_LIMIT"
    assert opened["payload"]["findings"][0]["recommendation"]["action"] == "Recover the overpaid amount"
    assert decision["kind"] == "decision" and decision["prev_hash"] == opened["hash"]
    assert decision["summary"] == "Confirmed discrepancy: Settlement overpayment"
    assert {k: decision["payload"][k] for k in ("previous", "status", "note")} == {
        "previous": "open",
        "status": "reviewed",
        "note": "Co-pay was missed",
    }
    assert view["integrity"] == {
        "verified": True,
        "events": 2,
        "head_hash": decision["hash"],
        "broken_at": None,
        "reason": None,
    }
    finding = view["findings"][0]
    assert finding["key"].startswith("ALR-") and decision["finding_key"] == finding["key"]
    assert finding["decision"]["status"] == "reviewed" and finding["decision"]["actor"] == "demo"
    assert Decimal(view["original"]["totals"]["calculated_leakage"]) == Decimal("4500")


def test_an_override_keeps_the_original_recommendation_and_the_reason(api: TestClient) -> None:  # noqa: F811
    alert = _processed(api)

    too_much = api.post(
        f"/api/v1/evidence/claims/{CLAIM}/overrides",
        json={"alert_id": alert["id"], "correction": "999999", "reason": "Wrong amount entered"},
    )
    no_reason = api.post(
        f"/api/v1/evidence/claims/{CLAIM}/overrides",
        json={"alert_id": alert["id"], "correction": "3000", "reason": "  ok "},
    )
    view = api.post(
        f"/api/v1/evidence/claims/{CLAIM}/overrides",
        json={"alert_id": alert["id"], "correction": "3000", "reason": "Provider refunded Rs 1,500 directly"},
    ).json()

    assert too_much.status_code == 422 and "cannot be more than" in too_much.json()["error"]["message"]
    assert no_reason.status_code == 422
    finding = view["findings"][0]
    assert Decimal(finding["original_recommendation"]["correction"]) == Decimal("4500")
    assert Decimal(finding["recommendation"]["correction"]) == Decimal("4500")
    assert Decimal(finding["effective_correction"]) == Decimal("3000")
    assert finding["override"]["reason"] == "Provider refunded Rs 1,500 directly"
    assert finding["override"]["reverted"] is False
    override = view["events"][0]
    assert override["kind"] == "override"
    assert Decimal(override["payload"]["original_recommendation"]["correction"]) == Decimal("4500")
    assert Decimal(override["payload"]["previous_correction"]) == Decimal("4500")
    assert override["summary"].startswith("Correction changed from ₹4,500 to ₹3,000")
    assert Decimal(view["summary"]["adjusted_calculated_leakage"]) == Decimal("3000")
    assert Decimal(view["summary"]["current_calculated_leakage"]) == Decimal("4500")
    assert view["summary"]["overrides"] == 1

    restored = api.post(
        f"/api/v1/evidence/claims/{CLAIM}/overrides",
        json={"alert_id": alert["id"], "correction": "4500", "reason": "Refund was not confirmed"},
    ).json()
    assert restored["findings"][0]["override"]["reverted"] is True
    assert restored["summary"]["overrides"] == 0
    assert restored["events"][0]["summary"].startswith("Correction restored to the recommended ₹4,500")
    assert [e["kind"] for e in reversed(restored["events"])] == ["opened", "override", "override"]


def test_overrides_and_history_survive_a_rerun(api: TestClient, sql) -> None:  # noqa: F811
    alert = _processed(api)
    api.post(
        f"/api/v1/evidence/claims/{CLAIM}/overrides",
        json={"alert_id": alert["id"], "correction": "4000", "reason": "Partial recovery agreed"},
    )

    api.post("/api/v1/runs", json={"scope": "all"})
    view = api.get(f"/api/v1/evidence/claims/{CLAIM}").json()

    new_alert_id = view["findings"][0]["alert_id"]
    assert new_alert_id != alert["id"]
    assert Decimal(view["findings"][0]["effective_correction"]) == Decimal("4000")
    # Nothing changed in the calculation, so the run adds no entry.
    assert [e["kind"] for e in reversed(view["events"])] == ["opened", "override"]
    assert view["integrity"]["verified"] is True

    # A changed policy changes the calculation: the run records what moved.
    sql("update policies set copay_percent = 0 where policy_number = 'POL-000001'")
    api.post("/api/v1/runs", json={"scope": "all"})
    view = api.get(f"/api/v1/evidence/claims/{CLAIM}").json()
    recalculated = view["events"][0]
    assert recalculated["kind"] == "recalculated" and recalculated["actor"] == "system"
    changes = recalculated["payload"]["changes"]
    assert changes["added"] or changes["removed"] or changes["changed"] or changes["payable"]
    assert view["integrity"]["verified"] is True


def test_notes_and_the_investigation_list(api: TestClient) -> None:  # noqa: F811
    alert = _processed(api)

    empty = api.post(f"/api/v1/evidence/claims/{CLAIM}/notes", json={"text": "   "})
    wrong_claim = api.post("/api/v1/evidence/claims/CLM-000002/notes", json={"text": "x", "alert_id": alert["id"]})
    view = api.post(
        f"/api/v1/evidence/claims/{CLAIM}/notes",
        json={"text": "Called the hospital billing desk", "alert_id": alert["id"]},
    ).json()
    listing = api.get("/api/v1/evidence").json()

    assert empty.status_code == 422
    assert wrong_claim.status_code == 404
    note = view["events"][0]
    assert note["kind"] == "note" and note["payload"]["text"] == "Called the hospital billing desk"
    assert note["finding_key"] == view["findings"][0]["key"]
    assert listing["total"] == 1
    row = listing["items"][0]
    assert row["claim_id"] == CLAIM and row["events"] == 2 and row["last_event_kind"] == "note"


def test_reports_are_recorded_and_cover_the_whole_history(api: TestClient) -> None:  # noqa: F811
    alert = _processed(api)
    api.patch(f"/api/v1/alerts/{alert['id']}", json={"status": "dismissed", "note": "Settled under appeal"})

    as_json = api.get(f"/api/v1/evidence/claims/{CLAIM}/report", params={"format": "json"})
    as_pdf = api.get(f"/api/v1/evidence/claims/{CLAIM}/report")

    assert as_json.status_code == 200
    assert as_json.headers["content-disposition"] == f'attachment; filename="investigation-{CLAIM}.json"'
    report = json.loads(as_json.content)
    assert report["report"]["schema_version"] == 1 and report["report"]["generated_by"] == "demo"
    assert [e["kind"] for e in report["evidence_history"]] == ["opened", "decision", "exported"]
    assert report["integrity"]["verified"] is True
    # The JSON report carries the full frozen snapshot, not the trimmed timeline copy.
    assert report["evidence_history"][0]["payload"]["lines"]
    assert report["findings"][0]["decision"]["status"] == "dismissed"
    assert as_pdf.headers["content-type"] == "application/pdf"
    assert as_pdf.content.startswith(b"%PDF")
    view = api.get(f"/api/v1/evidence/claims/{CLAIM}").json()
    assert [e["kind"] for e in view["events"][:2]] == ["exported", "exported"]


def test_entries_cannot_be_changed_in_the_database(api: TestClient, sql) -> None:  # noqa: F811
    alert = _processed(api)
    api.post(f"/api/v1/evidence/claims/{CLAIM}/notes", json={"text": "First look", "alert_id": alert["id"]})

    with pytest.raises(DBAPIError, match="append-only"):
        sql("update evidence_events set summary = 'edited' where seq = 2")
    with pytest.raises(DBAPIError, match="append-only"):
        sql("delete from evidence_events where seq = 2")


def test_verify_finds_edits_gaps_and_missing_entries() -> None:
    from datetime import UTC, datetime

    from app.evidence.chain import entry_hash

    events: list[EvidenceEvent] = []
    rows: list[dict] = []
    previous = None
    for seq, text in enumerate(["opened", "note one", "note two"], start=1):
        at = datetime(2026, 10, 31, 12, seq, tzinfo=UTC)
        fields = dict(
            claim_id=CLAIM,
            seq=seq,
            at=at,
            actor="demo",
            actor_role=None,
            kind="note",
            finding_key=None,
            alert_id=None,
            summary=text,
            payload={"text": text},
            prev_hash=previous,
        )
        digest = entry_hash(**fields)
        rows.append({**fields, "hash": digest})
        events.append(EvidenceEvent(**fields, hash=digest))
        previous = digest

    assert verify(events, previous).verified

    edited = [events[0], EvidenceEvent(**{**rows[1], "summary": "rewritten"}), events[2]]
    result = verify(edited, previous)
    assert not result.verified and result.broken_at == 2 and "changed" in result.reason

    assert verify([events[0], events[2]], previous).broken_at == 3
    assert verify(events[:2], previous).reason == "Latest entries are missing"
