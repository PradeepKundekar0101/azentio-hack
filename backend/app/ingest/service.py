"""One import: store the originals, read, validate, commit accepted rows, record every issue, reconcile."""

import asyncio
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import BatchStatus, IssueSeverity
from app.core.logging import get_logger
from app.db.models import Claim, ImportBatch, LineItem, Policy, PolicyRule, ServiceCode, Settlement
from app.ingest.commit import commit_rows
from app.ingest.mapping import Dataset
from app.ingest.readers import RawTable, ReadError, read_upload
from app.ingest.schemas import Code
from app.ingest.validate import ExistingData, TableIssue, reconciles, validate_tables
from app.storage.spaces import Storage

log = get_logger(__name__)


@dataclass
class UploadedFile:
    file_name: str
    content_type: str
    data: bytes


def _ids(tables: list[RawTable], *headers: str) -> list[str]:
    """Candidate identifiers from any column that could hold them, before mapping; only used to narrow lookups."""
    from app.ingest.mapping import compact

    wanted = {compact(h) for h in headers}
    found: set[str] = set()
    for table in tables:
        columns = [h for h in table.headers if compact(h) in wanted]
        for row in table.rows:
            for column in columns:
                value = row.values.get(column)
                if value is not None and str(value).strip():
                    found.add(str(value).strip())
    return sorted(found)


async def load_existing(session: AsyncSession, tables: list[RawTable]) -> ExistingData:
    policy_ids = _ids(tables, "policy_number", "policyno", "policynum")
    claim_ids = _ids(tables, "claim_id", "claimno", "claimnumber")
    existing = ExistingData()
    if policy_ids:
        rows = await session.execute(
            select(Policy.policy_number, Policy.insured_member_ids).where(Policy.policy_number.in_(policy_ids))
        )
        existing.policies = {number: list(members) for number, members in rows}
    rule_ids = _ids(tables, "rule_id", "ruleno")
    if rule_ids:
        existing.rule_ids = set(
            await session.scalars(select(PolicyRule.rule_id).where(PolicyRule.rule_id.in_(rule_ids)))
        )
    if claim_ids:
        rows = await session.execute(
            select(Claim.claim_id, Claim.status, Claim.incident_date, Claim.submission_date).where(
                Claim.claim_id.in_(claim_ids)
            )
        )
        existing.claims = {claim_id: (status, incident, submitted) for claim_id, status, incident, submitted in rows}
    line_ids = _ids(tables, "line_id", "lineno", "lineitemid")
    if line_ids:
        existing.line_ids = set(await session.scalars(select(LineItem.line_id).where(LineItem.line_id.in_(line_ids))))
    settlement_ids = _ids(tables, "settlement_id", "settlementno")
    if settlement_ids:
        existing.settlement_ids = set(
            await session.scalars(select(Settlement.settlement_id).where(Settlement.settlement_id.in_(settlement_ids)))
        )
    existing.service_codes = set(await session.scalars(select(ServiceCode.code)))
    return existing


async def run_import(
    session: AsyncSession,
    storage: Storage,
    files: list[UploadedFile],
    uploaded_by: str,
    dataset_hint: Dataset | None = None,
    today: date | None = None,
) -> ImportBatch:
    batch = ImportBatch(uploaded_by=uploaded_by, files=[], status=BatchStatus.RECEIVED.value, counts={})
    session.add(batch)
    await session.flush()

    stored = []
    for upload in files:
        key = await asyncio.to_thread(
            storage.upload, f"imports/{batch.id}/{upload.file_name}", upload.data, upload.content_type
        )
        stored.append(
            {
                "file_name": upload.file_name,
                "storage_key": key,
                "size": len(upload.data),
                "content_type": upload.content_type,
            }
        )

    tables: list[RawTable] = []
    unreadable: list[TableIssue] = []
    for upload, entry in zip(files, stored, strict=True):
        try:
            file_tables = read_upload(upload.file_name, upload.data, dataset_hint)
        except ReadError as exc:
            unreadable.append(
                TableIssue(upload.file_name, None, None, IssueSeverity.ERROR, Code.UNREADABLE_FILE, str(exc))
            )
            entry["datasets"] = []
            continue
        entry["datasets"] = sorted({t.dataset.value for t in file_tables if t.dataset})
        tables.extend(file_tables)

    existing = await load_existing(session, tables)
    result = validate_tables(tables, existing, today or date.today())
    result.table_issues[:0] = unreadable
    counts = result.counts()

    batch.files = stored
    batch.counts = counts
    if reconciles(counts):
        await commit_rows(session, result, batch.id)
        batch.status = BatchStatus.COMPLETED.value
    else:  # pragma: no cover - guards the invariant; validate_tables always assigns every row a status
        batch.status = BatchStatus.FAILED.value
        batch.error = "Row counts do not reconcile: received != accepted + warnings + rejected"
    await session.commit()
    log.info("import_finished", batch_id=batch.id, status=batch.status, counts=counts)
    return batch
