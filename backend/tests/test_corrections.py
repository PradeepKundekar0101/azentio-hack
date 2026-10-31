"""Recommended settlement corrections: sequenced corrections from re-running the payable calculator on a corrected line
set, reconciliation, versioning, and acceptance against the answer key (every planted scenario, the multi-issue claims
and the demo-script claim)."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.corrections.builder import CorrectionInputs, LineAction, ReconciliationError, Stop, build_corrections
from app.rules.context import ClaimData, LineData, PolicyData, RuleData
from app.rules.payable import evaluate_policy
from scripts.seed_reference import seed_reference
from tests.test_answer_key import import_and_run
from tests.test_comparison import NoAiMatches, attach_extractions
from tests.test_imports_api import MemoryStorage

DEMO = Path(__file__).resolve().parents[2] / "data" / "sample" / "demo"
D = date(2026, 3, 10)

pytestmark = pytest.mark.skipif(not (DEMO / "answer_key.json").exists(), reason="run make generate first")


# ---- the builder on a hand-computed example -------------------------------------------------------------------------

POLICY = PolicyData(
    "POL-1",
    ("M1",),
    date(2026, 1, 1),
    date(2026, 12, 31),
    Decimal("500000"),
    Decimal("2000"),
    "per_claim",
    Decimal("10"),
)
RULES = (
    RuleData("R-TYPE", "coverage", "claim_type", "inpatient", None, None, "Section 2.1"),
    *(
        RuleData(f"R-{c}", "coverage", "category", c, None, None, "Section 3")
        for c in ("room", "pharmacy", "procedure")
    ),
    RuleData("R-ROOM", "sub_limit", "category", "room", "per_day", Decimal("5000"), "Section 3.1 Room rent"),
)


def line(lid: str, code: str, category: str, qty: str, price: str) -> LineData:
    return LineData(lid, D, code, code, category, Decimal(qty), Decimal(price), Decimal(qty) * Decimal(price))


LINES = (
    line("L1", "RM-PVT", "room", "3", "7000"),
    line("L2", "PHA-ABX", "pharmacy", "1", "500"),
    line("L3", "PHA-ABX", "pharmacy", "1", "500"),  # repeats L2
    line("L4", "PRC-APPX", "procedure", "1", "30000"),
)


def claim(lines: tuple[LineData, ...] = LINES) -> ClaimData:
    return ClaimData("C1", "M1", D, D, "inpatient", sum((x.line_amount for x in lines), Decimal(0)), "open", lines)


def payable(corrected: list[LineData]):
    data = claim(tuple(corrected))
    (evaluation,) = evaluate_policy(POLICY, RULES, [data])
    return evaluation


def test_corrections_interact_and_never_double_count() -> None:
    plan = build_corrections(
        CorrectionInputs(claim(), [LineAction("L3", "REMOVE_DUPLICATE_LINE", Decimal(0), ["ALR-1"], "repeats L2")]),
        payable,
    )
    assert [(c.type, c.difference) for c in plan.applied] == [
        ("REMOVE_DUPLICATE_LINE", Decimal("500")),
        ("CAP_AT_SUB_LIMIT", Decimal("6000")),  # (7,000 - 5,000) x 3
        ("APPLY_DEDUCTIBLE", Decimal("2000")),
        ("APPLY_COPAY", Decimal("4350.00")),  # 10% of 43,500, after the repeated line is gone
    ]
    assert plan.recommended_payable == Decimal("39150.00")
    assert plan.requested - sum(c.difference for c in plan.applied) == plan.recommended_payable
    # Each step runs from the previous one's corrected amount.
    for before, after in zip(plan.applied, plan.applied[1:], strict=False):
        assert after.original_amount == before.corrected_amount
    cap = plan.applied[1]
    assert cap.policy_rule_id == "R-ROOM" and "7,000" in cap.calculation_text and cap.line_id == "L1"


def test_a_claim_level_stop_sets_the_payable_to_zero_and_nothing_else() -> None:
    plan = build_corrections(
        CorrectionInputs(claim(), [], stop=Stop("Exact duplicate of C0 (paid Rs 48,500).", ["ALR-9"])), payable
    )
    assert [(c.type, c.original_amount, c.corrected_amount) for c in plan.applied] == [
        ("SET_PAYABLE_TO_ZERO", Decimal("52000"), Decimal("0"))
    ]
    assert plan.recommended_payable == 0


def test_estimated_items_are_listed_but_never_change_the_payable() -> None:
    baseline = build_corrections(CorrectionInputs(claim(), []), payable)
    review = LineAction(
        "L4",
        "REMOVE_UNSUPPORTED_LINE",
        Decimal(0),
        ["DSC-1"],
        "not in the summary",
        applied=False,
        amount_type="estimated",
    )
    plan = build_corrections(CorrectionInputs(claim(), [review]), payable)
    assert plan.recommended_payable == baseline.recommended_payable
    (item,) = plan.for_review
    assert (item.type, item.applied, item.difference, item.amount_type) == (
        "REMOVE_UNSUPPORTED_LINE",
        False,
        Decimal("30000"),
        "estimated",
    )


def test_settled_claims_get_the_overpayment_to_recover() -> None:
    plan = build_corrections(CorrectionInputs(claim(), [], paid=Decimal("40000"), approved=Decimal("40000")), payable)
    recovery = plan.recovery
    assert recovery is not None and recovery.type == "RECOVER_OVERPAYMENT"
    assert recovery.difference == Decimal("40000") - plan.recommended_payable == plan.recovery_amount


def test_reconciliation_failures_raise() -> None:
    def broken(corrected: list[LineData]):
        evaluation = payable(corrected)
        evaluation.payable += Decimal("1")
        return evaluation

    with pytest.raises(ReconciliationError):
        build_corrections(CorrectionInputs(claim(), []), broken)


# ---- acceptance against the demo pack ----------------------------------------------------------------------------


def key() -> dict:
    return json.loads((DEMO / "answer_key.json").read_text())


@pytest.fixture
def corrected(settings: Settings, auth_client: TestClient) -> TestClient:
    seed_reference(settings)
    auth_client.app.state.storage = MemoryStorage()
    auth_client.app.state.reader = NoAiMatches()
    import_and_run(auth_client, DEMO, "csv")
    asyncio.run(attach_extractions(settings))
    run = auth_client.post("/api/v1/runs", json={"scope": "all"}).json()
    assert auth_client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "completed"
    return auth_client


EXPECTED_TYPES = {
    "excluded_service": ("REMOVE_EXCLUDED_LINE", True),
    "not_covered": (None, True),  # a category (line removed) or the claim type (claim stopped)
    "claimant_not_insured": ("SET_PAYABLE_TO_ZERO", True),
    "outside_benefit_period": ("SET_PAYABLE_TO_ZERO", True),
    "room_rent_above_per_day_limit": ("CAP_AT_SUB_LIMIT", True),
    "per_claim_sub_limit": ("CAP_AT_SUB_LIMIT", True),
    "per_period_sub_limit": ("CAP_AT_SUB_LIMIT", True),
    "overall_limit": ("CAP_AT_OVERALL_LIMIT", True),
    "settled_without_copay": ("RECOVER_OVERPAYMENT", True),
    "settled_without_deductible": ("RECOVER_OVERPAYMENT", True),
    "settled_above_approved": ("RECOVER_OVERPAYMENT", True),
    "exact_duplicate_claim": ("SET_PAYABLE_TO_ZERO", True),
    "duplicate_line_within_claim": ("REMOVE_DUPLICATE_LINE", True),
    "duplicate_line_across_claims": ("REMOVE_DUPLICATE_LINE", True),
    "near_duplicate": ("REMOVE_DUPLICATE_LINE", False),
}


def corrections_of(api: TestClient, claim_id: str) -> dict:
    response = api.get(f"/api/v1/claims/{claim_id}/corrections")
    assert response.status_code == 200, (claim_id, response.text)
    return response.json()


def test_every_planted_scenario_gets_its_correction(corrected: TestClient) -> None:
    misses = []
    for finding in key()["findings"]:
        expected_type, applied = EXPECTED_TYPES.get(finding["scenario"], (None, None))
        if applied is None:
            continue
        body = corrections_of(corrected, finding["claim_id"])
        amount = Decimal(finding["expected_amount"])
        candidates = [c for c in body["corrections"] if c["applied"] == applied]
        if expected_type:
            candidates = [c for c in candidates if c["type"] == expected_type]
        if expected_type == "SET_PAYABLE_TO_ZERO":
            ok = bool(candidates)  # the whole requested amount, whichever eligibility check failed first
        else:
            ok = any(abs(Decimal(c["difference"]) - amount) <= Decimal("1.00") for c in candidates)
        if not ok:
            misses.append(
                (
                    finding["scenario"],
                    finding["claim_id"],
                    str(amount),
                    [(c["type"], c["difference"]) for c in body["corrections"]],
                )
            )
    assert not misses, misses


def nonzero(items: list[dict]) -> list[tuple[str, Decimal]]:
    return [(c["type"], Decimal(c["amount"])) for c in items if Decimal(c["amount"]) != 0]


def test_multi_issue_and_demo_claims_match_their_worked_examples(corrected: TestClient) -> None:
    section = key()["investigation"]
    for example in [*section["multi_issue_claims"], section["showcase"]]:
        body = corrections_of(corrected, example["claim_id"])
        got = [(c["type"], Decimal(c["difference"])) for c in body["corrections"] if c["applied"]]
        assert got == nonzero(example["expected_corrections"]), (example["claim_id"], got)
        assert Decimal(body["recommended_payable"]) == Decimal(example["recommended_payable"])


def test_every_set_reconciles_and_every_row_explains_itself(corrected: TestClient, sql) -> None:
    sets = sql("select set_id, claim_id, requested_amount, recommended_payable, total_reduction from correction_sets")
    assert sets
    for set_id, claim_id, requested, recommended, reduction in sets:
        rows = sql(
            "select difference from corrections where set_id = :s and applied and type <> 'RECOVER_OVERPAYMENT'",
            s=set_id,
        )
        assert requested - sum((r[0] for r in rows), Decimal(0)) == recommended, claim_id
        assert reduction == requested - recommended
    rows = sql(
        "select correction_id, original_amount, corrected_amount, calculation_text, policy_rule_id, "
        "evidence_refs, type from corrections"
    )
    for correction_id, original, corrected_amount, text, rule_id, evidence, kind in rows:
        assert correction_id.startswith("COR-")
        assert original is not None and corrected_amount is not None and text
        # An uncovered line has no rule to cite: it fails because no coverage rule names it.
        if kind in ("CAP_AT_SUB_LIMIT", "REMOVE_EXCLUDED_LINE"):
            assert rule_id, (correction_id, kind)
        if kind in (
            "REMOVE_DUPLICATE_LINE",
            "REMOVE_UNSUPPORTED_LINE",
            "ADJUST_TO_DOCUMENT",
            "REDUCE_ROOM_DAYS",
            "SET_PAYABLE_TO_ZERO",
            "RECOVER_OVERPAYMENT",
        ):
            assert evidence, (correction_id, kind)


def test_recomputing_keeps_versions_and_a_changed_line_adds_one(corrected: TestClient, sql) -> None:
    claim_id = key()["investigation"]["showcase"]["claim_id"]
    current = corrections_of(corrected, claim_id)["version"]
    first = corrected.post(f"/api/v1/claims/{claim_id}/corrections/recompute").json()
    assert first["version"] == current and first["created"] is False
    sql(
        "update line_items set unit_price = 11000, line_amount = 11000 "
        "where claim_id = :c and service_code = 'PRC-HERN'",
        c=claim_id,
    )
    second = corrected.post(f"/api/v1/claims/{claim_id}/corrections/recompute").json()
    assert second["version"] == current + 1 and second["created"] is True
    versions = corrected.get(f"/api/v1/claims/{claim_id}/corrections/versions").json()
    assert [v["version"] for v in versions] == list(range(1, current + 2))
    old = corrected.get(f"/api/v1/claims/{claim_id}/corrections?version={current}").json()
    assert (
        Decimal(old["requested_amount"]) != Decimal(second["requested_amount"])
        or old["corrections"] != second["corrections"]
    )
    assert old["recommended_payable"] == key()["investigation"]["showcase"]["recommended_payable"]
    events = sql(
        "select count(*) from analysis_events where event_type = 'correction_set_created' and claim_id = :c", c=claim_id
    )
    assert events[0][0] == current + 1
