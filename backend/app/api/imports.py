import csv
import io
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.pagination import Page, PageDep
from app.core import audit
from app.core.enums import IssueSeverity
from app.core.errors import AppError, not_found
from app.core.security import CurrentUser
from app.db.models import ImportBatch, ImportIssue
from app.db.session import SessionDep
from app.ingest.mapping import Dataset
from app.ingest.service import UploadedFile, run_import
from app.storage.spaces import StorageDep

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 10


class DatasetCounts(BaseModel):
    received: int
    accepted: int
    warnings: int
    rejected: int


class ImportFileOut(BaseModel):
    file_name: str
    size: int
    content_type: str
    datasets: list[str] = []


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uploaded_by: str
    uploaded_at: datetime
    status: str
    files: list[ImportFileOut]
    counts: dict[str, DatasetCounts]
    totals: DatasetCounts
    error: str | None


class ImportIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset: str | None
    file_name: str
    sheet: str | None
    row_number: int | None
    field: str | None
    value: str | None
    severity: str
    code: str
    message: str


def _batch_out(batch: ImportBatch) -> ImportBatchOut:
    counts = {name: DatasetCounts(**values) for name, values in (batch.counts or {}).items()}
    totals = DatasetCounts(
        **{
            key: sum(getattr(c, key) for c in counts.values())
            for key in ("received", "accepted", "warnings", "rejected")
        }
    )
    return ImportBatchOut(
        id=batch.id,
        uploaded_by=batch.uploaded_by,
        uploaded_at=batch.uploaded_at,
        status=batch.status,
        files=[ImportFileOut(**f) for f in batch.files or []],
        counts=counts,
        totals=totals,
        error=batch.error,
    )


@router.post("", status_code=201)
async def create_import(
    session: SessionDep,
    storage: StorageDep,
    username: CurrentUser,
    files: Annotated[list[UploadFile], File(description="CSV, Excel (.xlsx) or JSON files")],
    dataset: Annotated[Dataset | None, Query(description="Dataset for a CSV or JSON array file")] = None,
) -> ImportBatchOut:
    if not files:
        raise AppError(400, "no_files", "Upload at least one file")
    if len(files) > MAX_FILES:
        raise AppError(400, "too_many_files", f"Upload at most {MAX_FILES} files at once")
    uploads: list[UploadedFile] = []
    for upload in files:
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise AppError(413, "payload_too_large", f"{upload.filename} is larger than 20 MB")
        name = (upload.filename or "upload").replace("/", "_").replace("\\", "_")
        uploads.append(UploadedFile(name, upload.content_type or "application/octet-stream", data))
    batch = await run_import(session, storage, uploads, uploaded_by=username, dataset_hint=dataset)
    audit.record(
        session,
        username,
        "import_uploaded",
        "import_batch",
        batch.id,
        files=[u.file_name for u in uploads],
        totals={k: v for k, v in (batch.counts or {}).items()},
    )
    await session.commit()
    await session.refresh(batch)
    return _batch_out(batch)


@router.get("")
async def list_imports(session: SessionDep, page: PageDep) -> Page[ImportBatchOut]:
    total = await session.scalar(select(func.count()).select_from(ImportBatch))
    batches = await session.scalars(
        select(ImportBatch).order_by(ImportBatch.id.desc()).offset(page.offset).limit(page.page_size)
    )
    return Page(items=[_batch_out(b) for b in batches], total=total or 0)


async def _get_batch(session: SessionDep, batch_id: int) -> ImportBatch:
    batch = await session.get(ImportBatch, batch_id)
    if batch is None:
        raise not_found("Import")
    return batch


@router.get("/{batch_id}")
async def get_import(batch_id: int, session: SessionDep) -> ImportBatchOut:
    return _batch_out(await _get_batch(session, batch_id))


def _issue_query(batch_id: int, dataset: str | None, severity: IssueSeverity | None) -> Any:
    query = select(ImportIssue).where(ImportIssue.batch_id == batch_id)
    if dataset:
        query = query.where(ImportIssue.dataset == dataset)
    if severity:
        query = query.where(ImportIssue.severity == severity.value)
    return query


@router.get("/{batch_id}/issues")
async def list_issues(
    batch_id: int,
    session: SessionDep,
    page: PageDep,
    dataset: str | None = None,
    severity: IssueSeverity | None = None,
) -> Page[ImportIssueOut]:
    await _get_batch(session, batch_id)
    query = _issue_query(batch_id, dataset, severity)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(query.order_by(ImportIssue.id).offset(page.offset).limit(page.page_size))
    return Page(items=[ImportIssueOut.model_validate(r) for r in rows], total=total or 0)


@router.get("/{batch_id}/issues.csv")
async def issues_csv(
    batch_id: int,
    session: SessionDep,
    dataset: str | None = None,
    severity: IssueSeverity | None = None,
) -> StreamingResponse:
    await _get_batch(session, batch_id)
    issues = list(await session.scalars(_issue_query(batch_id, dataset, severity).order_by(ImportIssue.id)))
    raw_headers: list[str] = []
    for issue in issues:
        for header in issue.raw_row or {}:
            if header not in raw_headers:
                raw_headers.append(header)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    fixed = ["dataset", "file_name", "sheet", "row_number", "severity", "code", "field", "value", "message"]
    writer.writerow(fixed + [f"original: {h}" for h in raw_headers])
    for issue in issues:
        raw = issue.raw_row or {}
        writer.writerow(
            [getattr(issue, name) for name in fixed]
            + ["|".join(map(str, v)) if isinstance(v := raw.get(h), list) else v for h in raw_headers]
        )
    content = "﻿" + buffer.getvalue()  # BOM so Excel opens UTF-8 (₹) correctly
    headers = {"Content-Disposition": f'attachment; filename="import-{batch_id}-issues.csv"'}
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers=headers)
