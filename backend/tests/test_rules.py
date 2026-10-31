from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from app.core.enums import Outcome
from app.rules.context import ClaimContext, ClaimData, LineData, PolicyData, PolicyLedger, RuleData, SettlementData
from app.rules.payable import evaluate, evaluate_policy

POLICY = PolicyData(
    policy_number="POL-000123",
    insured_member_ids=("MEM-001", "MEM-002"),
    benefit_period_start=date(2026, 1, 1),
    benefit_period_end=date(2026, 12, 31),
    overall_limit=D("500000"),
    deductible_amount=D("0"),
    deductible_basis="per_claim",
    copay_percent=D("0"),
)


def rule(rule_id: str, rule_type: str, scope_type: str, scope_value: str, basis=None, limit=None) -> RuleData:
    return RuleData(
        rule_id, rule_type, scope_type, scope_value, basis, D(limit) if limit else None, f"Clause {rule_id}"
    )


RULES = (
    rule("POL-000123-CV-01", "coverage", "claim_type", "inpatient"),
    rule("POL-000123-CV-02", "coverage", "category", "room"),
    rule("POL-000123-CV-03", "coverage", "category", "diagnostics"),
    rule("POL-000123-CV-04", "coverage", "category", "procedure"),
    rule("POL-000123-CV-05", "coverage", "category", "physiotherapy"),
    rule("POL-000123-EX-01", "exclusion", "service_code", "PRC-COSM"),
    rule("POL-000123-SL-01", "sub_limit", "category", "room", "per_day", "5000"),
    rule("POL-000123-SL-02", "sub_limit", "category", "diagnostics", "per_claim", "15000"),
    rule("POL-000123-SL-03", "sub_limit", "category", "physiotherapy", "per_period", "20000"),
)


def line(line_id: str, code: str, category: str, qty: str, price: str, day: int = 10) -> LineData:
    return LineData(line_id, date(2026, 3, day), code, code, category, D(qty), D(price), D(qty) * D(price))


def claim(*lines: LineData, claim_id="CLM-000001", **changes) -> ClaimData:
    base = ClaimData(
        claim_id=claim_id,
        claimant_id="MEM-001",
        incident_date=date(2026, 3, 10),
        submission_date=date(2026, 3, 15),
        claim_type="inpatient",
        requested_amount=sum((ln.line_amount for ln in lines), D(0)),
        status="open",
        lines=lines,
    )
    return replace(base, **changes)


def run(c: ClaimData, policy: PolicyData = POLICY, rules=RULES, ledger: PolicyLedger | None = None):
    return evaluate(ClaimContext(c, policy, rules, ledger or PolicyLedger()))


def result(evaluation, code: str):
    found = [r for r in evaluation.results if r.check_code == code]
    assert len(found) == 1, found
    return found[0]


def test_room_rent_example_reproduces_six_thousand() -> None:
    evaluation = run(claim(line("LN-1", "RM-PVT", "room", "3", "7000")))

    c06 = result(evaluation, "C06")
    assert c06.outcome is Outcome.FAIL
    assert c06.amount_impact == D("6000.00")
    assert c06.policy_rule_id == "POL-000123-SL-01"
    assert c06.inputs["formula"] == "(₹7,000 − ₹5,000) × 3 days = ₹6,000"
    assert "(₹7,000 − ₹5,000) × 3 = ₹6,000" in c06.explanation
    assert evaluation.payable == D("15000.00")


def test_room_rent_exactly_at_the_limit_passes() -> None:
    assert result(run(claim(line("LN-1", "RM-PVT", "room", "3", "5000"))), "C06").outcome is Outcome.PASS


def test_daily_room_lines_are_compared_per_date() -> None:
    lines = (line("LN-1", "RM-PVT", "room", "1", "6000", 10), line("LN-2", "RM-PVT", "room", "1", "4000", 11))

    evaluation = run(claim(*lines))

    impacts = [r.amount_impact for r in evaluation.results if r.check_code == "C06"]
    assert impacts == [D("1000.00"), D("0")]


def test_every_check_is_recorded_for_a_clean_claim() -> None:
    evaluation = run(
        claim(line("LN-1", "RM-GEN", "room", "2", "3000"), line("LN-2", "DX-CBC", "diagnostics", "1", "800"))
    )

    codes = {r.check_code for r in evaluation.results}
    assert codes == {f"C{n:02d}" for n in range(1, 13)}
    assert all(r.outcome in (Outcome.PASS, Outcome.NOT_APPLICABLE, Outcome.ADJUSTED) for r in evaluation.results)
    assert evaluation.payable == D("6800")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"incident_date": date(2025, 12, 31)}, "C01"),
        ({"claimant_id": "MEM-404"}, "C02"),
        ({"claim_type": "outpatient"}, "C03"),
    ],
)
def test_eligibility_failure_makes_the_full_amount_not_payable(changes: dict, code: str) -> None:
    evaluation = run(claim(line("LN-1", "RM-GEN", "room", "2", "3000"), **changes))

    failed = result(evaluation, code)
    assert failed.outcome is Outcome.FAIL
    assert failed.amount_impact == D("6000")
    assert evaluation.payable == 0
    assert result(evaluation, "C04").outcome is Outcome.NOT_APPLICABLE


def test_last_day_of_benefit_period_is_inside() -> None:
    evaluation = run(claim(line("LN-1", "RM-GEN", "room", "1", "3000"), incident_date=date(2026, 12, 31)))

    assert result(evaluation, "C01").outcome is Outcome.PASS


def test_two_eligibility_failures_count_the_amount_once() -> None:
    evaluation = run(claim(line("LN-1", "RM-GEN", "room", "1", "3000"), claimant_id="X", claim_type="outpatient"))

    assert sum(r.amount_impact for r in evaluation.results if r.outcome is Outcome.FAIL) == D("3000")


def test_uncovered_and_excluded_lines() -> None:
    lines = (
        line("LN-1", "RM-GEN", "room", "1", "3000"),
        line("LN-2", "PHA-ABX", "pharmacy", "1", "900"),
        line("LN-3", "PRC-COSM", "procedure", "1", "40000"),
    )

    evaluation = run(claim(*lines))

    by_line = {(r.check_code, r.line_id): r for r in evaluation.results}
    assert by_line[("C04", "LN-2")].amount_impact == D("900")
    assert by_line[("C05", "LN-2")].outcome is Outcome.NOT_APPLICABLE
    assert by_line[("C05", "LN-3")].amount_impact == D("40000")
    assert by_line[("C05", "LN-3")].policy_rule_id == "POL-000123-EX-01"
    assert evaluation.payable == D("3000")


def test_per_claim_sub_limit() -> None:
    lines = (line("LN-1", "DX-MRI", "diagnostics", "1", "12000"), line("LN-2", "DX-CT", "diagnostics", "1", "6000"))

    c07 = result(run(claim(*lines)), "C07")

    assert c07.amount_impact == D("3000.00")


def test_per_period_sub_limit_uses_earlier_claims() -> None:
    first = claim(line("LN-1", "PHY-SES", "physiotherapy", "10", "1500"), claim_id="CLM-000001")
    second = claim(
        line("LN-2", "PHY-SES", "physiotherapy", "6", "1500", 20),
        claim_id="CLM-000002",
        incident_date=date(2026, 3, 20),
        submission_date=date(2026, 3, 25),
    )

    evaluations = evaluate_policy(POLICY, RULES, [second, first])

    assert [e.claim_id for e in evaluations] == ["CLM-000001", "CLM-000002"]
    c08 = result(evaluations[1], "C08")
    assert c08.amount_impact == D("4000.00")  # 9,000 against the 5,000 left of 20,000
    assert c08.inputs["used_by_earlier_claims"] == "15000.00"


def test_deductible_and_copay_are_adjustments_in_order() -> None:
    policy = replace(POLICY, deductible_amount=D("5000"), copay_percent=D("10"))

    evaluation = run(claim(line("LN-1", "RM-GEN", "room", "4", "5000")), policy)

    assert result(evaluation, "C09").outcome is Outcome.ADJUSTED
    assert result(evaluation, "C09").amount_impact == D("5000")
    assert result(evaluation, "C10").amount_impact == D("1500.00")
    assert evaluation.payable == D("13500.00")
    assert [s.step_code for s in evaluation.steps] == [
        "ELIGIBILITY",
        "COVERAGE",
        "SUB_LIMITS",
        "C09 DEDUCTIBLE",
        "C10 COPAY",
        "C11 OVERALL_LIMIT",
    ]


def test_zero_deductible_and_zero_copay_are_not_applicable() -> None:
    evaluation = run(claim(line("LN-1", "RM-GEN", "room", "1", "3000")))

    assert result(evaluation, "C09").outcome is Outcome.NOT_APPLICABLE
    assert result(evaluation, "C10").outcome is Outcome.NOT_APPLICABLE


def test_per_period_deductible_is_shared_across_claims() -> None:
    policy = replace(POLICY, deductible_amount=D("5000"), deductible_basis="per_period")
    first = claim(line("LN-1", "RM-GEN", "room", "1", "3000"), claim_id="CLM-000001")
    second = claim(
        line("LN-2", "RM-GEN", "room", "1", "3000", 20), claim_id="CLM-000002", incident_date=date(2026, 3, 20)
    )

    evaluations = evaluate_policy(policy, RULES, [first, second])

    assert [result(e, "C09").amount_impact for e in evaluations] == [D("3000"), D("2000")]


def test_overall_limit_counts_settled_paid_amounts() -> None:
    policy = replace(POLICY, overall_limit=D("300000"))
    settled = claim(
        line("LN-1", "PRC-APPX", "procedure", "1", "290000"),
        claim_id="CLM-000001",
        status="settled",
        settlement=SettlementData("STL-1", date(2026, 3, 30), D("295000"), D("295000"), "paid"),
    )
    later = claim(
        line("LN-2", "RM-GEN", "room", "4", "3000", 20), claim_id="CLM-000002", incident_date=date(2026, 3, 20)
    )

    evaluations = evaluate_policy(policy, RULES, [later, settled])

    c11 = result(evaluations[1], "C11")
    assert c11.amount_impact == D("7000")  # 12,000 against the 5,000 left after 2,95,000 paid
    assert evaluations[1].payable == D("5000")


def test_settled_claim_paid_without_copay_is_an_overpayment() -> None:
    policy = replace(POLICY, copay_percent=D("10"))
    settled = claim(
        line("LN-1", "PRC-APPX", "procedure", "1", "84000"),
        status="settled",
        settlement=SettlementData("STL-1", date(2026, 3, 30), D("84000"), D("84000"), "paid"),
    )

    c12 = result(run(settled, policy), "C12")

    assert c12.outcome is Outcome.FAIL
    assert c12.amount_impact == D("8400.00")
    assert "co-pay of ₹8,400 not applied" in c12.explanation
    assert "Paid ₹84,000; entitlement ₹75,600" in c12.explanation


def test_settled_claim_paid_above_approved() -> None:
    settled = claim(
        line("LN-1", "PRC-APPX", "procedure", "1", "50000"),
        status="settled",
        settlement=SettlementData("STL-1", date(2026, 3, 30), D("45000"), D("50000"), "paid"),
    )

    c12 = result(run(settled), "C12")

    assert c12.amount_impact == D("5000")


def test_correctly_paid_settlement_passes() -> None:
    policy = replace(POLICY, copay_percent=D("10"))
    settled = claim(
        line("LN-1", "PRC-APPX", "procedure", "1", "84000"),
        status="settled",
        settlement=SettlementData("STL-1", date(2026, 3, 30), D("75600"), D("75600"), "paid"),
    )

    assert result(run(settled, policy), "C12").outcome is Outcome.PASS
