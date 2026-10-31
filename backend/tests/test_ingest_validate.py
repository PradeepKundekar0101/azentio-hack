from datetime import date

import pytest

from app.ingest.mapping import Dataset, compact, dataset_from_name, map_headers
from app.ingest.readers import read_upload
from app.ingest.schemas import Code, parse_date
from app.ingest.validate import ExistingData, RowStatus, ValidationResult, reconciles, validate_tables
from scripts.seed_reference import load_reference_rows
from tests.ingest_fixtures import BASE, dataset, to_csv, to_csv_files, to_json, to_xlsx

TODAY = date(2026, 10, 31)
SERVICE_CODES = {row["code"] for row in load_reference_rows()[0]}


def validate(files: list[tuple[str, bytes]], existing: ExistingData | None = None) -> ValidationResult:
    tables = [table for name, data in files for table in read_upload(name, data)]
    known = existing or ExistingData()
    known.service_codes = known.service_codes or SERVICE_CODES
    return validate_tables(tables, known, TODAY)


def codes(result: ValidationResult, ds: Dataset) -> list[list[str]]:
    return [[issue.code.value for issue in row.issues] for row in result.rows[ds]]


def test_clean_dataset_is_fully_accepted() -> None:
    result = validate(to_csv_files(BASE))

    counts = result.counts()
    assert all(c["accepted"] == c["received"] for c in counts.values()), counts
    assert reconciles(counts)
    assert not result.table_issues


@pytest.mark.parametrize("render", ["csv", "xlsx", "json"])
def test_all_formats_produce_identical_values(render: str) -> None:
    files = {
        "csv": to_csv_files(BASE),
        "xlsx": [("claims_data.xlsx", to_xlsx(BASE))],
        "json": [("claims_data.json", to_json(BASE))],
    }[render]
    reference = validate(to_csv_files(BASE))

    result = validate(files)

    for ds in Dataset:
        assert [r.values for r in result.rows[ds]] == [r.values for r in reference.rows[ds]]
        assert all(r.status is RowStatus.ACCEPTED for r in result.rows[ds])


def test_headers_match_case_spacing_and_synonyms() -> None:
    header_map = map_headers(
        Dataset.CLAIMS,
        [
            "Claim No",
            "POLICY NO",
            "Member ID",
            "Patient Name",
            "Date Of Incident",
            "Submitted Date",
            "claim_type",
            "ClaimAmount",
            "Claim Status",
            "Ward",
        ],
    )

    assert header_map.missing == []
    assert header_map.unknown == ["Ward"]
    assert header_map.columns["Claim No"] == "claim_id"
    assert compact("Claim-ID") == "claimid"
    assert dataset_from_name("claim_lines") is Dataset.LINE_ITEMS
    assert dataset_from_name("Policy Rules") is Dataset.POLICY_RULES


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2026-03-10", date(2026, 3, 10)), ("10-03-2026", date(2026, 3, 10)), ("1/3/2026", date(2026, 3, 1))],
)
def test_dates_in_accepted_formats(text: str, expected: date) -> None:
    assert parse_date(text) == expected


def test_csv_with_semicolons_and_latin1_is_read() -> None:
    data = to_csv(BASE["policies"], delimiter=";").decode().replace("Ravi", "Rávi").encode("latin-1")

    result = validate([("policies.csv", data)])

    assert result.rows[Dataset.POLICIES][0].values["policyholder_name"] == "Rávi Kumar"
    assert result.rows[Dataset.POLICIES][0].status is RowStatus.ACCEPTED


def _bad_claim(**fields: str) -> dict:
    return {**BASE["claims"][1], **fields}


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"claimant_name": ""}, Code.MISSING_FIELD),
        ({"requested_amount": "-500"}, Code.NEGATIVE_AMOUNT),
        ({"requested_amount": "1.42.000"}, Code.INVALID_AMOUNT),
        ({"incident_date": "31-02-2026"}, Code.INVALID_DATE),
        ({"incident_date": "03/04/26"}, Code.AMBIGUOUS_DATE),
        ({"submission_date": "2026-05-01"}, Code.SUBMISSION_BEFORE_INCIDENT),
        ({"policy_number": "POL-999999"}, Code.UNKNOWN_POLICY),
        ({"claim_id": "CLM-12"}, Code.INVALID_FORMAT),
        ({"claim_type": "dental"}, Code.INVALID_VALUE),
        ({"incident_date": "2026-11-15", "submission_date": "2026-11-16"}, Code.FUTURE_DATE),
    ],
)
def test_claim_errors_reject_the_row(fields: dict, code: Code) -> None:
    records = dataset(claims=[BASE["claims"][0], _bad_claim(**fields)])

    result = validate(to_csv_files(records))

    row = result.rows[Dataset.CLAIMS][1]
    assert row.status is RowStatus.REJECTED
    assert code in [i.code for i in row.issues]


def test_a_row_reports_all_its_problems_together() -> None:
    records = dataset(claims=[_bad_claim(claimant_name="", requested_amount="-1", claim_type="x")])

    result = validate(to_csv_files(records))

    assert sorted(codes(result, Dataset.CLAIMS)[0]) == ["invalid_value", "missing_field", "negative_amount"]


def test_rejected_claim_rejects_its_lines_with_the_reason() -> None:
    records = dataset(claims=[BASE["claims"][0], _bad_claim(requested_amount="-5")])

    result = validate(to_csv_files(records))

    line = result.rows[Dataset.LINE_ITEMS][2]
    assert line.status is RowStatus.REJECTED
    assert line.issues[0].code is Code.PARENT_REJECTED
    assert line.issues[0].message == "parent claim rejected: CLM-000002"


def test_line_errors() -> None:
    lines = [dict(line) for line in BASE["line_items"]]
    lines[0]["line_amount"] = "25000"
    lines[1]["service_code"] = "XX-NONE"
    lines[2]["claim_id"] = "CLM-000777"
    lines.append({**lines[1], "service_code": "DX-CBC"})  # duplicate of LN-0000002's id

    result = validate(to_csv_files(dataset(line_items=lines)))

    assert codes(result, Dataset.LINE_ITEMS) == [
        ["line_amount_mismatch"],
        ["unknown_service_code"],
        ["unknown_claim"],
        ["duplicate_id_in_file"],
    ]


def test_warnings_keep_the_row() -> None:
    claims = [dict(c) for c in BASE["claims"]]
    claims[1]["claimant_id"] = "MEM-404"
    claims[1]["requested_amount"] = "25000"
    settlements = [{**BASE["settlements"][0], "paid_amount": "16,000"}]

    result = validate(to_csv_files(dataset(claims=claims, settlements=settlements)))

    claim = result.rows[Dataset.CLAIMS][1]
    assert claim.status is RowStatus.WARNINGS
    assert sorted(i.code.value for i in claim.issues) == ["claimant_not_insured", "requested_amount_mismatch"]
    assert result.rows[Dataset.SETTLEMENTS][0].issues[0].code is Code.PAID_ABOVE_APPROVED
    assert result.rows[Dataset.SETTLEMENTS][0].status is RowStatus.WARNINGS


def test_settlement_for_an_open_claim_is_rejected() -> None:
    settlements = [{**BASE["settlements"][0], "claim_id": "CLM-000002", "settlement_date": "2026-06-01"}]

    result = validate(to_csv_files(dataset(settlements=settlements)))

    assert codes(result, Dataset.SETTLEMENTS) == [["claim_not_settled"]]


def test_ids_already_in_the_database_are_rejected() -> None:
    existing = ExistingData(policies={"POL-000001": ["MEM-001"]})

    result = validate(to_csv_files(dataset()), existing)

    assert codes(result, Dataset.POLICIES) == [["id_exists"]]
    # The stored policy still satisfies references, so its rules and claims are accepted.
    assert result.rows[Dataset.POLICY_RULES][0].status is RowStatus.ACCEPTED


def test_missing_required_column_rejects_the_whole_dataset_with_one_issue() -> None:
    claims = [{k: v for k, v in c.items() if k != "claim_type"} for c in BASE["claims"]]

    result = validate(to_csv_files(dataset(claims=claims)))

    assert [i.code for i in result.table_issues] == [Code.MISSING_COLUMN]
    assert "claim_type" in result.table_issues[0].message
    assert all(r.status is RowStatus.REJECTED and not r.issues for r in result.rows[Dataset.CLAIMS])
    assert result.counts()["claims"] == {"received": 2, "accepted": 0, "warnings": 0, "rejected": 2}
    assert reconciles(result.counts())


def test_unknown_columns_are_kept_as_extra_with_a_warning() -> None:
    policies = [{**BASE["policies"][0], "Agent Code": "AG-7"}]

    result = validate(to_csv_files(dataset(policies=policies)))

    row = result.rows[Dataset.POLICIES][0]
    assert row.status is RowStatus.ACCEPTED
    assert row.source_row["extra"] == {"Agent Code": "AG-7"}
    assert [(i.code, i.field) for i in result.table_issues] == [(Code.UNKNOWN_COLUMN, "Agent Code")]


def test_unrecognised_file_is_counted_not_dropped() -> None:
    result = validate([("notes.csv", b"colour,size\nred,10\nblue,12\n")])

    assert result.counts()["unrecognised"] == {"received": 2, "accepted": 0, "warnings": 0, "rejected": 2}
    assert result.table_issues[0].code is Code.UNKNOWN_DATASET
