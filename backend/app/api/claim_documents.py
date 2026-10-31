"""Supporting documents of a claim: upload (classified and extracted in the background), list, read an extraction
with the source of every value, override the type to re-extract, and a short-lived link to the file."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.core.errors import AppError, not_found
from app.core.security import get_current_user
from app.db.models import Claim, Document, DocumentExtraction, ExtractedField, ExtractedLine
from app.db.session import SessionDep
from app.documents.claim_documents import latest_extraction, process_claim_document, store_claim_document
from app.documents.parse import sniff_type
from app.storage.spaces import StorageDep

router = APIRouter(tags=["claim documents"], dependencies=[Depends(get_current_user)])
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
PRESIGN_SECONDS = 300


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClaimDocumentOut(Orm):
    id: int
    claim_id: str | None
    file_name: str
    file_type: str
    size_bytes: int
    sha256: str
    phash: str | None
    doc_type: str | None
    page_count: int | None
    parse_status: str
    created_at: datetime
    latest_extraction_version: int | None = None
    latest_extraction_status: str | None = None


class FieldOut(Orm):
    field_path: str
    value_text: str | None
    value_normalised: str | None
    page: int | None
    bbox: dict[str, float] | None
    source_quote: str | None
    provenance_status: str
    confidence: Decimal


class ExtractedLineOut(Orm):
    line_no: int
    description: str | None
    service_code: str | None
    service_date: date | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    page: int | None
    bbox: dict[str, float] | None


class ExtractionOut(Orm):
    extraction_id: int
    document_id: int
    version: int
    doc_type: str
    schema_version: str
    model: str
    prompt_version: str
    status: str
    route: str
    attempts: int
    validation_errors: list[str] | None
    classification_confidence: Decimal | None
    error: str | None
    generated_by: str
    created_at: datetime
    fields: list[FieldOut] = []
    lines: list[ExtractedLineOut] = []


class DocTypeIn(BaseModel):
    doc_type: Literal["invoice", "discharge_summary", "repair_estimate"]


class FileLinkOut(BaseModel):
    url: str
    expires_in: int


async def _with_versions(session: SessionDep, documents: list[Document]) -> list[ClaimDocumentOut]:
    ids = [d.id for d in documents]
    latest: dict[int, tuple[int, str]] = {}
    if ids:
        newest = (
            select(DocumentExtraction.document_id, func.max(DocumentExtraction.version).label("version"))
            .where(DocumentExtraction.document_id.in_(ids))
            .group_by(DocumentExtraction.document_id)
            .subquery()
        )
        rows = await session.execute(
            select(DocumentExtraction.document_id, DocumentExtraction.version, DocumentExtraction.status).join(
                newest,
                (DocumentExtraction.document_id == newest.c.document_id)
                & (DocumentExtraction.version == newest.c.version),
            )
        )
        latest = {doc_id: (version, status) for doc_id, version, status in rows}
    out = []
    for document in documents:
        item = ClaimDocumentOut.model_validate(document)
        item.latest_extraction_version, item.latest_extraction_status = latest.get(document.id, (None, None))
        out.append(item)
    return out


@router.post("/claims/{claim_id}/documents", status_code=201)
async def upload_claim_document(
    claim_id: str,
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> ClaimDocumentOut:
    if await session.get(Claim, claim_id) is None:
        raise not_found("Claim")
    data = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise AppError(413, "file_too_large", "Documents can be at most 15 MB")
    file_type = sniff_type(data)
    if file_type is None:
        raise AppError(415, "unsupported_file", "Upload a PDF, PNG or JPEG file")
    document = await store_claim_document(session, storage, claim_id, file.filename or "document", file_type, data)
    app = request.app
    background.add_task(
        process_claim_document, app.state.db, storage, app.state.reader, app.state.settings, document.id, None
    )
    return (await _with_versions(session, [document]))[0]


@router.get("/claims/{claim_id}/documents")
async def list_claim_documents(claim_id: str, session: SessionDep) -> list[ClaimDocumentOut]:
    if await session.get(Claim, claim_id) is None:
        raise not_found("Claim")
    documents = list(await session.scalars(select(Document).where(Document.claim_id == claim_id).order_by(Document.id)))
    return await _with_versions(session, documents)


async def extraction_out(session: SessionDep, extraction: DocumentExtraction) -> ExtractionOut:
    fields = await session.scalars(
        select(ExtractedField)
        .where(ExtractedField.extraction_id == extraction.extraction_id)
        .order_by(ExtractedField.id)
    )
    lines = await session.scalars(
        select(ExtractedLine)
        .where(ExtractedLine.extraction_id == extraction.extraction_id)
        .order_by(ExtractedLine.line_no)
    )
    out = ExtractionOut.model_validate(extraction)
    out.fields = [FieldOut.model_validate(f) for f in fields]
    out.lines = [ExtractedLineOut.model_validate(ln) for ln in lines]
    return out


@router.get("/documents/{document_id}/extraction")
async def get_extraction(
    document_id: int, session: SessionDep, version: Annotated[int | None, Query(ge=1)] = None
) -> ExtractionOut:
    extraction = await latest_extraction(session, document_id, version)
    if extraction is None:
        raise not_found("Extraction")
    return await extraction_out(session, extraction)


@router.patch("/documents/{document_id}")
async def set_document_type(
    document_id: int,
    body: DocTypeIn,
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    background: BackgroundTasks,
) -> ClaimDocumentOut:
    """Override the classified type; the document is extracted again as a new version."""
    document = await session.get(Document, document_id)
    if document is None or document.claim_id is None:
        raise not_found("Document")
    document.doc_type = body.doc_type
    await session.commit()
    app = request.app
    background.add_task(
        process_claim_document, app.state.db, storage, app.state.reader, app.state.settings, document.id, body.doc_type
    )
    return (await _with_versions(session, [document]))[0]


@router.get("/documents/{document_id}/file")
async def document_file(document_id: int, session: SessionDep, storage: StorageDep) -> FileLinkOut:
    document = await session.get(Document, document_id)
    if document is None:
        raise not_found("Document")
    name = document.storage_key.removeprefix(storage.key(""))
    url = await asyncio.to_thread(storage.presigned_download_url, name, PRESIGN_SECONDS)
    return FileLinkOut(url=url, expires_in=PRESIGN_SECONDS)
