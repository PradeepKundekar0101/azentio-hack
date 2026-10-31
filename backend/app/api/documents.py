import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.pagination import Page, PageDep
from app.api.runs import RunOut
from app.core import audit
from app.core.enums import ParseStatus, RunScope
from app.core.errors import AppError, not_found
from app.core.security import CurrentUser
from app.db.models import Document
from app.db.session import SessionDep
from app.documents.parse import sniff_type
from app.documents.service import confirm_document, process_document, store_document
from app.pipeline import run_in_background, start_run
from app.storage.spaces import StorageDep

router = APIRouter(prefix="/documents", tags=["documents"])
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: str | None
    file_name: str
    file_type: str
    size_bytes: int
    sha256: str
    parse_status: str
    confidence: Decimal | None
    issues: list[str] | None
    created_at: datetime


class DocumentDetail(DocumentOut):
    extracted: dict[str, Any] | None
    file_url: str


class ConfirmLine(BaseModel):
    service_date: str | None = None
    service_code: str | None = None
    service_description: str | None = None
    category: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    line_amount: str | None = None


class ConfirmClaim(BaseModel):
    policy_number: str | None = None
    claimant_id: str | None = None
    claimant_name: str | None = None
    incident_date: str | None = None
    submission_date: str | None = None
    claim_type: str | None = None
    requested_amount: str | None = None
    incident_reference: str | None = None


class ConfirmIn(BaseModel):
    claim: ConfirmClaim
    invoice_reference: str | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    lines: list[ConfirmLine] = Field(min_length=1)


class ConfirmOut(BaseModel):
    claim_id: str
    batch_id: int
    run: RunOut


@router.post("", status_code=201)
async def upload_document(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Invoice as PDF, PNG or JPEG, up to 15 MB")],
) -> DocumentOut:
    data = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise AppError(413, "payload_too_large", "The document is larger than 15 MB")
    file_type = sniff_type(data)
    if file_type is None:
        raise AppError(415, "unsupported_media_type", "Upload a PDF, PNG or JPEG file")
    name = (file.filename or f"document.{file_type}").replace("/", "_").replace("\\", "_")
    document = await store_document(session, storage, name, file_type, data)
    state = request.app.state
    background.add_task(process_document, state.db, state.storage, state.extractor, document.id)
    return DocumentOut.model_validate(document)


@router.get("")
async def list_documents(session: SessionDep, page: PageDep) -> Page[DocumentOut]:
    total = await session.scalar(select(func.count()).select_from(Document))
    rows = await session.scalars(
        select(Document).order_by(Document.id.desc()).offset(page.offset).limit(page.page_size)
    )
    return Page(items=[DocumentOut.model_validate(d) for d in rows], total=total or 0)


@router.get("/{document_id}")
async def get_document(document_id: int, session: SessionDep, storage: StorageDep) -> DocumentDetail:
    document = await session.get(Document, document_id)
    if document is None:
        raise not_found("Document")
    name = document.storage_key.removeprefix(storage.key(""))
    url = await asyncio.to_thread(storage.presigned_download_url, name)
    return DocumentDetail.model_validate(
        {**DocumentOut.model_validate(document).model_dump(), "extracted": document.extracted, "file_url": url}
    )


@router.post("/{document_id}/confirm")
async def confirm(
    document_id: int,
    body: ConfirmIn,
    request: Request,
    session: SessionDep,
    username: CurrentUser,
    background: BackgroundTasks,
) -> ConfirmOut:
    document = await session.get(Document, document_id)
    if document is None:
        raise not_found("Document")
    if document.parse_status == ParseStatus.CONFIRMED.value:
        raise AppError(409, "already_confirmed", f"Document already confirmed as claim {document.claim_id}")
    if document.parse_status == ParseStatus.PENDING.value:
        raise AppError(409, "still_processing", "The document is still being read")
    result, batch, claim_id = await confirm_document(session, document, body.model_dump(), username)
    if batch is None:
        problems = [
            {
                "dataset": ds.value,
                "row": row.row_number,
                "field": issue.field,
                "code": issue.code.value,
                "message": issue.message,
            }
            for ds, rows in result.rows.items()
            for row in rows
            for issue in row.issues
            if issue.severity.value == "error"
        ]
        raise AppError(
            422, "validation_failed", "The claim did not pass validation; fix the fields and confirm again", problems
        )
    audit.record(session, username, "document_confirmed", "document", document.id, claim_id=claim_id, batch_id=batch.id)
    run = await start_run(session, RunScope.BATCH, batch.id)
    app = request.app
    background.add_task(run_in_background, app.state.db, app.state.settings, run.id, app.state.reader)
    return ConfirmOut(claim_id=claim_id, batch_id=batch.id, run=RunOut.model_validate(run))
