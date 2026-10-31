import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from scripts.seed_reference import seed_reference
from tests.ingest_fixtures import BASE, dataset, to_csv_files, to_json, to_xlsx


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def key(self, name: str) -> str:
        return f"test/{name}"

    def upload(self, name: str, body: bytes, content_type: str) -> str:
        self.objects[name] = body
        return self.key(name)

    def download(self, name: str) -> bytes:
        return self.objects[name]

    def presigned_download_url(self, name: str, expires_in: int = 300) -> str:
        return f"https://storage.test/{self.key(name)}?expires={expires_in}"


@pytest.fixture
def api(settings: Settings, auth_client: TestClient) -> TestClient:
    seed_reference(settings)
    auth_client.app.state.storage = MemoryStorage()
    return auth_client


def upload(client: TestClient, files: list[tuple[str, bytes]]):
    return client.post("/api/v1/imports", files=[("files", (name, data)) for name, data in files])


def test_upload_commits_accepted_rows_and_reconciles(api: TestClient, sql) -> None:
    response = upload(api, to_csv_files(BASE))

    body = response.json()
    assert response.status_code == 201, body
    assert body["status"] == "completed"
    assert body["counts"]["line_items"] == {"received": 3, "accepted": 3, "warnings": 0, "rejected": 0}
    assert body["totals"]["received"] == 11
    assert sql("select count(*) from claims")[0][0] == 2
    norm, source = sql("select invoice_reference_norm, source_row from line_items where line_id = 'LN-0000001'")[0]
    assert norm == "INV452"
    assert source == {"file_name": "line_items.csv", "sheet": None, "row_number": 2}
    assert set(api.app.state.storage.objects) == {f"imports/{body['id']}/{n}.csv" for n in BASE}


@pytest.mark.parametrize("fmt", ["xlsx", "json"])
def test_every_format_stores_identical_records(api: TestClient, sql, fmt: str) -> None:
    files = [("data.xlsx", to_xlsx(BASE))] if fmt == "xlsx" else [("data.json", to_json(BASE))]
    query = """select claim_id, policy_number, claimant_id, incident_date, submission_date, requested_amount, status
               from claims order by claim_id"""

    assert upload(api, to_csv_files(BASE)).json()["status"] == "completed"
    from_csv = sql(query)
    sql("truncate claims, policies, policy_rules, line_items, settlements cascade")
    assert upload(api, files).json()["status"] == "completed"

    assert sql(query) == from_csv


def test_issues_are_listed_filtered_and_downloadable(api: TestClient) -> None:
    claims = [BASE["claims"][0], {**BASE["claims"][1], "requested_amount": "-5", "claimant_name": ""}]
    batch = upload(api, to_csv_files(dataset(claims=claims))).json()

    issues = api.get(f"/api/v1/imports/{batch['id']}/issues", params={"dataset": "claims"}).json()
    lines = api.get(f"/api/v1/imports/{batch['id']}/issues", params={"dataset": "line_items"}).json()
    report = api.get(f"/api/v1/imports/{batch['id']}/issues.csv")

    assert issues["total"] == 2
    assert {i["code"] for i in issues["items"]} == {"negative_amount", "missing_field"}
    assert lines["items"][0]["message"] == "parent claim rejected: CLM-000002"
    assert batch["counts"]["claims"]["rejected"] == 1
    rows = list(csv.DictReader(io.StringIO(report.content.decode("utf-8-sig"))))
    assert report.headers["content-type"].startswith("text/csv")
    assert len(rows) == 3
    assert rows[0]["original: requested_amount"] == "-5"


def test_reimporting_the_same_ids_rejects_them_as_existing(api: TestClient) -> None:
    upload(api, to_csv_files(BASE))

    second = upload(api, to_csv_files(BASE)).json()

    assert second["totals"]["rejected"] == second["totals"]["received"]
    issues = api.get(f"/api/v1/imports/{second['id']}/issues", params={"dataset": "policies"}).json()
    assert issues["items"][0]["code"] == "id_exists"


def test_batches_are_listed_newest_first(api: TestClient) -> None:
    first = upload(api, to_csv_files(BASE)).json()
    second = upload(api, [("notes.csv", b"a,b\n1,2\n")]).json()

    listed = api.get("/api/v1/imports").json()

    assert [b["id"] for b in listed["items"]] == [second["id"], first["id"]]
    assert api.get(f"/api/v1/imports/{first['id']}").json()["files"][0]["datasets"] == ["policies"]
    assert api.get("/api/v1/imports/9999").status_code == 404


def test_unsupported_file_type_is_reported(api: TestClient) -> None:
    batch = upload(api, [("scan.pdf", b"%PDF-1.7")]).json()

    issues = api.get(f"/api/v1/imports/{batch['id']}/issues").json()
    assert issues["items"][0]["code"] == "unreadable_file"
