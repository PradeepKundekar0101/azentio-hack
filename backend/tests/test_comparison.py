"""Document-to-claim comparison: line matching, discrepancy rules, and acceptance against every planted document
discrepancy in the demo pack (type, line and amount, nothing extra)."""

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import Document
from app.db.session import Database
from app.documents.claim_documents import store_extraction
from app.documents.compare import ClaimLineView, DocLineView, line_findings, stay_findings
from app.documents.extract_sourced import ExtractionResult, FieldResult, LineResult
from app.documents.matching import assign_lines, similarity
from app.documents.schemas import LineMatchDecision, ProcedureCheck
from scripts.seed_reference import seed_reference
from tests.test_answer_key import import_and_run
from tests.test_imports_api import MemoryStorage

DEMO = Path(__file__).resolve().parents[2] / "data" / "sample" / "demo"
D = date(2026, 3, 10)

pytestmark = pytest.mark.skipif(not (DEMO / "answer_key.json").exists(), reason="run make generate first")


def cl(lid: str, code: str, desc: str, qty: str, price: str, day: date = D, category: str = "diagnostics"):
    return ClaimLineView(
        lid, "INV-1", code, desc, category, day, Decimal(qty), Decimal(price), Decimal(qty) * Decimal(price)
    )


def dl(no: int, code: str | None, desc: str, qty: str, price: str, day: date = D, status: str = "verified"):
    return DocLineView(
        no,
        code,
        desc,
        day,
        Decimal(qty),
        Decimal(price),
        Decimal(qty) * Decimal(price),
        1,
        {"l": 0.1, "t": 0.2, "r": 0.9, "b": 0.22},
        status,
        f"{desc} {price}",
    )


# ---- matching ----------------------------------------------------------------------------------------------------


def test_similarity_weights_code_description_amount_and_date() -> None:
    same = similarity(cl("L1", "DX-CT", "CT scan", "1", "4000"), dl(1, "DX-CT", "CT scan", "1", "4000"))
    assert same == pytest.approx(1.0)
    no_code = similarity(cl("L1", "DX-CT", "CT scan", "1", "4000"), dl(1, None, "CT scan", "1", "4000"))
    assert no_code == pytest.approx(0.60)


def test_lines_are_assigned_one_to_one_and_the_rest_left_over() -> None:
    claim = [
        cl("L1", "DX-CT", "CT scan", "1", "4000"),
        cl("L2", "DX-CBC", "Complete blood count", "1", "350"),
        cl("L3", "OTH-AMB", "Ambulance charges", "1", "1200"),
    ]
    doc = [
        dl(1, "DX-CBC", "Complete blood count", "1", "350"),
        dl(2, "DX-CT", "CT scan", "1", "3200"),
        dl(3, "CS-DRS", "Dressing material", "2", "90"),
    ]
    result = assign_lines(claim, doc)
    assert {(p.claim.line_id, p.doc.line_no) for p in result.pairs} == {("L1", 2), ("L2", 1)}
    assert [c.line_id for c in result.unmatched_claim] == ["L3"]
    assert [d.line_no for d in result.unmatched_document] == [3]


def test_borderline_pairs_are_left_for_the_model() -> None:
    claim = [cl("L1", "DX-CT", "CT Brain Plain", "1", "4000")]
    doc = [dl(1, None, "CT Head without contrast", "1", "4000")]
    result = assign_lines(claim, doc)
    assert not result.pairs
    assert [(c.claim.line_id, c.doc.line_no) for c in result.candidates] == [("L1", 1)]
    assert 0.40 <= result.candidates[0].score < 0.60


# ---- discrepancy rules -------------------------------------------------------------------------------------------


def kinds(findings) -> list[tuple[str, Decimal | None]]:
    return sorted((f.type, f.amount_impact) for f in findings)


def test_single_quantity_price_difference_is_an_amount_mismatch() -> None:
    findings = line_findings(
        cl("L1", "PRC-HERN", "Hernia repair", "1", "12000"), dl(1, "PRC-HERN", "Hernia repair", "1", "9500")
    )
    assert kinds(findings) == [("AMOUNT_MISMATCH", Decimal("2500"))]
    assert findings[0].amount_type == "calculated"


def test_quantity_and_unit_price_mismatches_add_up_to_the_difference() -> None:
    claim, doc = cl("L1", "PHA-ABX", "Antibiotics", "4", "250"), dl(1, "PHA-ABX", "Antibiotics", "3", "200")
    findings = line_findings(claim, doc)
    assert kinds(findings) == [("QUANTITY_MISMATCH", Decimal("250")), ("UNIT_PRICE_MISMATCH", Decimal("150"))]
    assert sum(f.amount_impact for f in findings) == claim.amount - doc.amount


def test_dates_differ_informationally_and_page_only_amounts_are_estimates() -> None:
    findings = line_findings(
        cl("L1", "PHA-ABX", "Antibiotics", "1", "500"),
        dl(1, "PHA-ABX", "Antibiotics", "1", "400", day=date(2026, 3, 11), status="page_only"),
    )
    by_type = {f.type: f for f in findings}
    assert by_type["SERVICE_DATE_MISMATCH"].amount_impact is None
    assert by_type["AMOUNT_MISMATCH"].amount_type == "estimated"


def test_room_days_beyond_the_documented_stay() -> None:
    lines = [cl("L1", "RM-PVT", "Private room", "5", "4000", category="room"), cl("L2", "CON-VIS", "Visit", "5", "800")]
    (finding,) = stay_findings(lines, date(2026, 3, 10), date(2026, 3, 13))
    assert (finding.type, finding.amount_impact, finding.claim_line.line_id) == (
        "STAY_LENGTH_MISMATCH",
        Decimal("8000"),
        "L1",
    )
    assert stay_findings(lines, date(2026, 3, 10), date(2026, 3, 15)) == []


# ---- acceptance --------------------------------------------------------------------------------------------------


class NoAiMatches:
    """The model's part: it rejects borderline line matches and finds no support for undocumented procedures."""

    model = "fake-reader"
    enabled = True

    def __init__(self) -> None:
        self.procedure_checks: list[str] = []

    async def same_service(self, claim_description: str, document_description: str) -> LineMatchDecision:
        return LineMatchDecision(same_service=False, confidence=0.9)

    async def check_procedure(self, procedure: str, summary_text: str) -> ProcedureCheck:
        self.procedure_checks.append(procedure)
        return ProcedureCheck(supported=False, quote=None)


def key() -> dict[str, Any]:
    return json.loads((DEMO / "answer_key.json").read_text())


def extraction_from_key(doc: dict[str, Any]) -> ExtractionResult:
    """What a perfect extraction of a generated document stores (scans: values read by vision, page only)."""
    status = "page_only" if doc["kind"] == "scan" else "verified"
    box = None if status == "page_only" else {"l": 0.1, "t": 0.1, "r": 0.5, "b": 0.12}
    e = doc["expected"]
    fields: list[FieldResult] = []

    def add(path: str, value: Any, normalised: Any = None) -> None:
        if value is None:
            return
        fields.append(
            FieldResult(
                path,
                str(value),
                str(normalised if normalised is not None else value),
                1,
                box,
                str(value),
                status,
                Decimal("1.000"),
            )
        )

    lines: list[LineResult] = []
    if doc["doc_type"] == "invoice":
        for name in (
            "invoice_number",
            "provider_name",
            "invoice_date",
            "patient_name",
            "policy_number",
            "admission_date",
            "total",
        ):
            add(f"header.{name}", e[name])
        for i, ln in enumerate(e["lines"]):
            code = None if doc["layout"] in ("B", "scan") else ln["service_code"]
            for name, value in (
                ("description", ln["description"]),
                ("service_code", code),
                ("service_date", ln["service_date"]),
                ("quantity", ln["quantity"]),
                ("unit_price", ln["unit_price"]),
                ("amount", ln["amount"]),
            ):
                add(f"lines[{i}].{name}", value)
            lines.append(
                LineResult(
                    i + 1,
                    ln["description"],
                    code,
                    ln["service_date"],
                    Decimal(ln["quantity"]),
                    Decimal(ln["unit_price"]),
                    Decimal(ln["amount"]),
                    1,
                    box,
                )
            )
    else:
        for name in (
            "patient_name",
            "hospital_name",
            "admission_date",
            "discharge_date",
            "diagnosis",
            "icd10",
            "treating_doctor",
        ):
            add(f"header.{name}", e[name])
        for i, text in enumerate(e["procedures_performed"]):
            add(f"procedures[{i}]", text)
    text = "\n".join(str(f.value_text) for f in fields)
    return ExtractionResult(
        doc["doc_type"],
        "ok",
        "vision" if status == "page_only" else "text",
        1,
        fields,
        lines,
        source_text=text if status == "verified" else None,
    )


async def attach_extractions(settings: Settings) -> None:
    database = Database(settings)
    async with database.sessionmaker() as session:
        for doc in key()["investigation"]["documents"]:
            document = Document(
                claim_id=doc["claim_id"],
                storage_key=f"test/{doc['file']}",
                sha256=doc["file"],
                file_name=doc["file"],
                file_type="png" if doc["kind"] == "scan" else "pdf",
                size_bytes=1,
                parse_status="pending",
                page_count=1,
            )
            session.add(document)
            await session.flush()
            await store_extraction(session, document, extraction_from_key(doc), "fake-reader")
        await session.commit()
    await database.dispose()


@pytest.fixture
def compared(settings: Settings, auth_client: TestClient) -> TestClient:
    seed_reference(settings)
    auth_client.app.state.storage = MemoryStorage()
    auth_client.app.state.reader = NoAiMatches()
    import_and_run(auth_client, DEMO, "csv")
    asyncio.run(attach_extractions(settings))
    run = auth_client.post("/api/v1/runs", json={"scope": "all"}).json()
    assert auth_client.get(f"/api/v1/runs/{run['id']}").json()["status"] == "completed"
    return auth_client


def test_every_planted_document_discrepancy_is_found_and_nothing_else(compared: TestClient, sql) -> None:
    expected = {
        (d["claim_id"], d["file"], d["type"], d["line_id"]): d for d in key()["investigation"]["document_discrepancies"]
    }
    claims = sorted({d["claim_id"] for d in key()["investigation"]["documents"]})
    found: dict[tuple, dict] = {}
    for claim_id in claims:
        body = compared.get(f"/api/v1/claims/{claim_id}/document-comparison").json()
        for comparison in body["comparisons"]:
            for disc in comparison["discrepancies"]:
                k = (claim_id, comparison["document"]["file_name"], disc["type"], disc["claim_ref"].get("line_id"))
                assert k not in found, k
                found[k] = disc
    missing = sorted(set(expected) - set(found))
    extra = sorted(set(found) - set(expected))
    assert not missing, missing
    assert not extra, [(k, found[k]["explanation"]) for k in extra]
    for k, item in expected.items():
        disc = found[k]
        amount = Decimal(item["expected_amount"]) if item["expected_amount"] else None
        impact = Decimal(disc["amount_impact"]) if disc["amount_impact"] is not None else None
        assert impact == amount, (k, impact, amount)
        assert disc["amount_type"] == item["amount_type"], (k, disc["amount_type"])
        # Every discrepancy points at its document, page and (for PDFs) the box of the value.
        ref = disc["document_ref"]
        assert ref["document_id"] and ref["page"] == 1, k
        if not k[1].endswith(".png") and disc["type"] not in ("ONLY_IN_CLAIM", "PROCEDURE_NOT_DOCUMENTED"):
            assert ref["bbox"], k
        assert disc["discrepancy_id"].startswith("DSC-")


def test_ai_procedure_checks_are_labelled_and_alerts_and_events_are_written(compared: TestClient, sql) -> None:
    procedures = [
        d for d in key()["investigation"]["document_discrepancies"] if d["type"] == "PROCEDURE_NOT_DOCUMENTED"
    ]
    for item in procedures:
        body = compared.get(f"/api/v1/claims/{item['claim_id']}/document-comparison").json()
        disc = next(
            d for c in body["comparisons"] for d in c["discrepancies"] if d["type"] == "PROCEDURE_NOT_DOCUMENTED"
        )
        assert disc["generated_by"] == "ai" and disc["model"] == "fake-reader"
        assert "quote" in disc["document_ref"]
        detail = compared.get(f"/api/v1/discrepancies/{disc['discrepancy_id']}").json()
        assert detail["discrepancy_id"] == disc["discrepancy_id"] and detail["claim_line"]["line_id"] == item["line_id"]
    amounts = [d for d in key()["investigation"]["document_discrepancies"] if d["expected_amount"]]
    alerts = sql("select claim_id, amount, amount_type, supporting from alerts where category = 'DOCUMENT_DISCREPANCY'")
    assert sorted((a[0], a[1]) for a in alerts) == sorted(
        (d["claim_id"], Decimal(d["expected_amount"])) for d in amounts
    )
    assert all(a[3]["discrepancy_id"].startswith("DSC-") for a in alerts)
    events = sql("select count(*) from analysis_events where event_type = 'comparison_created'")[0][0]
    assert events == len(key()["investigation"]["documents"])


def test_rerunning_with_unchanged_inputs_keeps_the_comparison(compared: TestClient, sql) -> None:
    before = sql("select count(*) from document_comparisons")[0][0]
    run = compared.post("/api/v1/runs", json={"scope": "all"}).json()
    assert compared.get(f"/api/v1/runs/{run['id']}").json()["status"] == "completed"
    assert sql("select count(*) from document_comparisons")[0][0] == before
    assert sql("select count(*) from alerts where category = 'DOCUMENT_DISCREPANCY'")[0][0] > 0
