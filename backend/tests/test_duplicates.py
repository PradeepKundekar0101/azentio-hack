from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app.db.models import Claim, LineItem
from app.duplicates.detect import CodeRule, find_duplicates
from app.duplicates.normalise import normalise_reference

CODES = {
    "PHY-SES": CodeRule("Physiotherapy session", True, 2, 3),
    "CON-FUP": CodeRule("Follow-up consultation", True, 7, 1),
    "DX-CBC": CodeRule("Complete blood count", False, None, None),
    "DX-LFT": CodeRule("Liver function test", False, None, None),
    "RM-GEN": CodeRule("General ward room (per day)", True, 1, 7),
}
START = date(2026, 3, 1)


@pytest.mark.parametrize(("raw", "norm"), [("INV-00452", "INV452"), ("inv 452", "INV452"), ("INV452A", "INV452A")])
def test_normalise_reference(raw: str, norm: str) -> None:
    assert normalise_reference(raw) == norm


def make(claim_id: str, day: int, lines: list[tuple], claimant="MEM-001", incident_ref=None, amount=None) -> tuple:
    claim = Claim(
        claim_id=claim_id,
        policy_number="POL-000001",
        claimant_id=claimant,
        claimant_name="Ravi Kumar",
        incident_date=START + timedelta(days=day),
        submission_date=START + timedelta(days=day + 2),
        claim_type="outpatient",
        incident_reference=incident_ref,
        incident_reference_norm=normalise_reference(incident_ref),
        status="open",
    )
    items = []
    for n, (code, invoice, offset, qty, price) in enumerate(lines, start=1):
        items.append(
            LineItem(
                line_id=f"{claim_id}-L{n}",
                claim_id=claim_id,
                invoice_reference=invoice,
                invoice_reference_norm=normalise_reference(invoice),
                provider_id="PRV-0001",
                provider_name="Greenleaf",
                service_date=START + timedelta(days=day + offset),
                service_code=code,
                service_description=CODES[code].description,
                category="other",
                quantity=D(qty),
                unit_price=D(price),
                line_amount=D(qty) * D(price),
            )
        )
    claim.requested_amount = amount if amount is not None else sum((i.line_amount for i in items), D(0))
    return claim, items


def detect(*claims: tuple, settled: dict | None = None) -> list[dict]:
    loaded = {"claim_rows": [c for c, _ in claims], "line_rows": [ln for _, lines in claims for ln in lines]}
    return find_duplicates(1, loaded, settled or {}, CODES, D("0.80"))


def kinds(matches: list[dict]) -> list[tuple]:
    return [(m["match_type"], m["decision"], m["claim_id"], m["matched_claim_id"]) for m in matches]


def test_exact_duplicate_same_invoice_flags_the_later_claim() -> None:
    original = make("CLM-000001", 0, [("DX-CBC", "INV-00452", 0, "1", "800")])
    resubmitted = make("CLM-000002", 10, [("DX-CBC", "inv 452", 0, "1", "800")])

    matches = detect(resubmitted, original, settled={"CLM-000001": (D("800"), date(2026, 3, 20))})

    assert kinds(matches) == [("exact_claim", "flagged", "CLM-000002", "CLM-000001")]
    assert "already paid ₹800 on 20 Mar 2026" not in matches[0]["reason"]  # original claim is open in this test


def test_exact_duplicate_by_incident_reference() -> None:
    a = make("CLM-000001", 0, [("DX-CBC", "INV-1", 0, "1", "800")], incident_ref="ACC-77")
    b = make("CLM-000002", 0, [("DX-LFT", "INV-2", 0, "1", "800")], incident_ref="acc 77")
    b[0].submission_date += timedelta(days=5)

    assert kinds(detect(a, b))[0][:2] == ("exact_claim", "flagged")


def test_duplicate_line_within_a_claim() -> None:
    claim = make("CLM-000001", 0, [("DX-CBC", "INV-1", 0, "1", "800"), ("DX-CBC", "INV-1", 0, "1", "800")])

    matches = detect(claim)

    assert [(m["match_type"], m["line_id"], m["matched_line_id"]) for m in matches] == [
        ("duplicate_line", "CLM-000001-L2", "CLM-000001-L1")
    ]


def test_room_lines_on_different_days_are_not_duplicates() -> None:
    claim = make("CLM-000001", 0, [("RM-GEN", "INV-1", 0, "1", "3000"), ("RM-GEN", "INV-1", 1, "1", "3000")])

    assert detect(claim) == []


def test_duplicate_line_across_claims() -> None:
    a = make("CLM-000001", 0, [("DX-CBC", "INV-9", 0, "1", "800"), ("DX-LFT", "INV-9", 0, "1", "900")])
    b = make(
        "CLM-000002",
        20,
        [("DX-CBC", "INV-9", -20, "1", "800"), ("PHY-SES", "INV-30", 0, "1", "1000")],
        claimant="MEM-002",
    )

    matches = detect(a, b)

    assert [(m["match_type"], m["claim_id"], m["line_id"]) for m in matches] == [
        ("duplicate_line", "CLM-000002", "CLM-000002-L1")
    ]


def test_near_duplicate_with_signals() -> None:
    a = make("CLM-000001", 0, [("DX-CBC", "INV-00452", 0, "1", "1000"), ("DX-LFT", "INV-00452", 0, "1", "1000")])
    b = make("CLM-000002", 2, [("DX-CBC", "INV452A", 0, "1", "1015"), ("DX-LFT", "INV452A", 0, "1", "1015")])

    matches = detect(a, b)

    assert kinds(matches) == [("near_duplicate", "flagged", "CLM-000002", "CLM-000001")]
    signals = matches[0]["signals"]
    assert signals["date_gap_days"] == 2
    assert signals["overlapping_amount"] == "2030.00"
    assert matches[0]["score"] >= D("0.80")


def test_weekly_physiotherapy_is_cleared_as_a_legitimate_repeat() -> None:
    a = make("CLM-000001", 0, [("PHY-SES", "PT-1001", 0, "1", "1200")])
    b = make("CLM-000002", 7, [("PHY-SES", "PT-2087", 0, "1", "1200")])

    matches = detect(a, b)

    assert kinds(matches) == [("legitimate_repeat", "cleared", "CLM-000002", "CLM-000001")]
    assert "7-day gap meets the 2-day minimum, different invoices" in matches[0]["reason"]


def test_repeatable_service_above_weekly_maximum_is_flagged() -> None:
    claims = [make(f"CLM-00000{n}", n * 2, [("PHY-SES", f"PT-{n}0{n}7", 0, "1", "1200")]) for n in range(1, 5)]
    claims.append(make("CLM-000009", 5, [("PHY-SES", "PT-9999", 0, "1", "1200")]))

    flagged = [m for m in detect(*claims) if m["decision"] == "flagged"]

    assert flagged and flagged[0]["signals"]["excess_frequency"] is True
    assert "frequency above expected" in flagged[0]["reason"]


def test_different_claimants_never_match_as_near_duplicates() -> None:
    a = make("CLM-000001", 0, [("DX-CBC", "INV-1", 0, "1", "1000")])
    b = make("CLM-000002", 1, [("DX-CBC", "INV-2", 0, "1", "1000")], claimant="MEM-002")

    assert detect(a, b) == []
