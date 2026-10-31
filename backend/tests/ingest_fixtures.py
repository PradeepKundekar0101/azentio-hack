"""A small, clean, hand-made dataset and helpers to render it as CSV, Excel or JSON uploads."""

import copy
import csv
import io
import json
from typing import Any

from openpyxl import Workbook

Records = dict[str, list[dict[str, Any]]]

BASE: Records = {
    "policies": [
        {
            "policy_number": "POL-000001",
            "policyholder_name": "Ravi Kumar",
            "insured_member_ids": ["MEM-001", "MEM-002"],
            "product_name": "Gold",
            "benefit_period_start": "2026-01-01",
            "benefit_period_end": "2026-12-31",
            "overall_limit": "5,00,000",
            "deductible_amount": "5000",
            "deductible_basis": "per_claim",
            "copay_percent": "10",
        }
    ],
    "policy_rules": [
        {
            "rule_id": "POL-000001-CV-01",
            "policy_number": "POL-000001",
            "rule_type": "coverage",
            "scope_type": "claim_type",
            "scope_value": "inpatient",
            "limit_basis": "",
            "limit_amount": "",
            "clause_ref": "Section 2.1 Hospitalisation",
            "description": "Inpatient treatment is covered",
        },
        {
            "rule_id": "POL-000001-CV-02",
            "policy_number": "POL-000001",
            "rule_type": "coverage",
            "scope_type": "category",
            "scope_value": "room",
            "limit_basis": "",
            "limit_amount": "",
            "clause_ref": "Section 2.2 Room",
            "description": "",
        },
        {
            "rule_id": "POL-000001-CV-03",
            "policy_number": "POL-000001",
            "rule_type": "coverage",
            "scope_type": "category",
            "scope_value": "diagnostics",
            "limit_basis": "",
            "limit_amount": "",
            "clause_ref": "Section 2.3 Diagnostics",
            "description": "",
        },
        {
            "rule_id": "POL-000001-SL-01",
            "policy_number": "POL-000001",
            "rule_type": "sub_limit",
            "scope_type": "category",
            "scope_value": "room",
            "limit_basis": "per_day",
            "limit_amount": "5000",
            "clause_ref": "Section 3.2 Room rent",
            "description": "",
        },
    ],
    "claims": [
        {
            "claim_id": "CLM-000001",
            "policy_number": "POL-000001",
            "claimant_id": "MEM-001",
            "claimant_name": "Ravi Kumar",
            "incident_date": "2026-03-10",
            "submission_date": "15-03-2026",
            "claim_type": "inpatient",
            "requested_amount": "₹23,000",
            "incident_reference": "ADM-2026-0001",
            "status": "settled",
        },
        {
            "claim_id": "CLM-000002",
            "policy_number": "POL-000001",
            "claimant_id": "MEM-002",
            "claimant_name": "Asha Kumar",
            "incident_date": "2026-05-02",
            "submission_date": "05/05/2026",
            "claim_type": "inpatient",
            "requested_amount": "21000.00",
            "incident_reference": "",
            "status": "open",
        },
    ],
    "line_items": [
        {
            "line_id": "LN-0000001",
            "claim_id": "CLM-000001",
            "invoice_reference": "INV-00452",
            "provider_id": "PRV-0001",
            "provider_name": "Greenleaf Multispeciality Hospital",
            "service_date": "2026-03-10",
            "service_code": "RM-PVT",
            "service_description": "Private room (per day)",
            "category": "room",
            "quantity": "3",
            "unit_price": "7,000",
            "line_amount": "21,000",
        },
        {
            "line_id": "LN-0000002",
            "claim_id": "CLM-000001",
            "invoice_reference": "INV-00452",
            "provider_id": "PRV-0001",
            "provider_name": "Greenleaf Multispeciality Hospital",
            "service_date": "2026-03-11",
            "service_code": "DX-CBC",
            "service_description": "Complete blood count",
            "category": "diagnostics",
            "quantity": "1",
            "unit_price": "2000",
            "line_amount": "2000.00",
        },
        {
            "line_id": "LN-0000003",
            "claim_id": "CLM-000002",
            "invoice_reference": "INV 7781",
            "provider_id": "PRV-0002",
            "provider_name": "Arogya Niketan Hospital",
            "service_date": "02-05-2026",
            "service_code": "RM-GEN",
            "service_description": "General ward room (per day)",
            "category": "room",
            "quantity": "7",
            "unit_price": "3000",
            "line_amount": "21000",
        },
    ],
    "settlements": [
        {
            "settlement_id": "STL-0000001",
            "claim_id": "CLM-000001",
            "settlement_date": "2026-04-01",
            "approved_amount": "15,300",
            "paid_amount": "15,300",
            "settlement_status": "paid",
        }
    ],
}


def dataset(**changes: list[dict[str, Any]]) -> Records:
    records = copy.deepcopy(BASE)
    records.update(copy.deepcopy(changes))
    return records


def _text(value: Any) -> str:
    return "|".join(value) if isinstance(value, list) else str(value)


def to_csv(rows: list[dict[str, Any]], headers: dict[str, str] | None = None, delimiter: str = ",") -> bytes:
    names = list(rows[0])
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow([(headers or {}).get(n, n) for n in names])
    for row in rows:
        writer.writerow([_text(row.get(n, "")) for n in names])
    return buffer.getvalue().encode("utf-8")


def to_csv_files(records: Records) -> list[tuple[str, bytes]]:
    return [(f"{name}.csv", to_csv(rows)) for name, rows in records.items() if rows]


def to_xlsx(records: Records, header_style: str = "title") -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in records.items():
        if not rows:
            continue
        sheet = workbook.create_sheet(name.replace("_", " ").title() if header_style == "title" else name)
        names = list(rows[0])
        sheet.append([n.replace("_", " ").title() if header_style == "title" else n for n in names])
        for row in rows:
            sheet.append([_text(row.get(n, "")) for n in names])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def to_json(records: Records) -> bytes:
    return json.dumps({name: rows for name, rows in records.items() if rows}, ensure_ascii=False).encode("utf-8")
