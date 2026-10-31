"""Insert accepted rows and every issue for one import batch, in a single transaction."""

from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import enums
from app.db.models import Claim, ImportIssue, LineItem, Policy, PolicyRule, Settlement
from app.duplicates.normalise import normalise_reference
from app.ingest.mapping import LOAD_ORDER, Dataset
from app.ingest.validate import Row, ValidationResult

MODELS = {
    Dataset.POLICIES: Policy,
    Dataset.POLICY_RULES: PolicyRule,
    Dataset.CLAIMS: Claim,
    Dataset.LINE_ITEMS: LineItem,
    Dataset.SETTLEMENTS: Settlement,
}

INSERT_CHUNK = 2000


def _record(dataset: Dataset, row: Row, batch_id: int, source: enums.ClaimSource) -> dict[str, Any]:
    record = dict(row.values)
    record["import_batch_id"] = batch_id
    record["source_row"] = row.source_row
    if dataset is Dataset.CLAIMS:
        record["incident_reference_norm"] = normalise_reference(record.get("incident_reference"))
        record["source"] = source.value
    elif dataset is Dataset.LINE_ITEMS:
        record["invoice_reference_norm"] = normalise_reference(record["invoice_reference"]) or ""
    return record


def _issue_rows(result: ValidationResult, batch_id: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for table_issue in result.table_issues:
        issues.append(
            {
                "batch_id": batch_id,
                "dataset": table_issue.dataset,
                "file_name": table_issue.file_name,
                "sheet": table_issue.sheet,
                "row_number": None,
                "field": table_issue.field,
                "value": None,
                "severity": table_issue.severity.value,
                "code": table_issue.code.value,
                "message": table_issue.message,
                "raw_row": None,
            }
        )
    for dataset in LOAD_ORDER:
        for row in result.rows.get(dataset, []):
            for issue in row.issues:
                issues.append(
                    {
                        "batch_id": batch_id,
                        "dataset": dataset.value,
                        "file_name": row.file_name,
                        "sheet": row.sheet,
                        "row_number": row.row_number,
                        "field": issue.field,
                        "value": issue.value,
                        "severity": issue.severity.value,
                        "code": issue.code.value,
                        "message": issue.message,
                        "raw_row": {k: _jsonable(v) for k, v in row.raw.items()},
                    }
                )
    return issues


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | bool | list):
        return value
    return str(value)


async def _insert(session: AsyncSession, model: type, records: list[dict[str, Any]]) -> None:
    for start in range(0, len(records), INSERT_CHUNK):
        # Core insert keeps every row's columns identical, so rows go out in large batches (see pipeline._insert).
        await session.execute(insert(model.__table__), records[start : start + INSERT_CHUNK])


async def commit_rows(
    session: AsyncSession,
    result: ValidationResult,
    batch_id: int,
    source: enums.ClaimSource = enums.ClaimSource.FILE,
) -> None:
    for dataset in LOAD_ORDER:
        records = [_record(dataset, row, batch_id, source) for row in result.accepted(dataset)]
        if records:
            await _insert(session, MODELS[dataset], records)
    await _insert(session, ImportIssue, _issue_rows(result, batch_id))
