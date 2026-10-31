"""Supporting documents attached to a claim: store the upload, then extract it in the background and store every
extraction as a new version with its fields, lines and an extraction_created event."""

import asyncio
import hashlib
import io
from datetime import date

from PIL import Image
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import ActorType, EventType, ExtractionStatus, GeneratedBy, ParseStatus
from app.core.logging import get_logger
from app.db.models import Document, DocumentExtraction, ExtractedField, ExtractedLine
from app.db.session import Database
from app.documents.comparison_service import compare_claim
from app.documents.extract_sourced import ExtractionResult, Reader, extract_document
from app.documents.parse import FILE_TYPES, page_count, parse_items
from app.documents.phash import phash
from app.documents.read import PROMPT_VERSION
from app.documents.schemas import SCHEMA_VERSION
from app.events import event, write_events
from app.graph.service import build_graph
from app.storage.spaces import Storage

log = get_logger(__name__)
EXTENSIONS = {"pdf": "pdf", "png": "png", "jpeg": "jpg"}
PARSE_STATUS = {
    ExtractionStatus.OK.value: ParseStatus.EXTRACTED.value,
    ExtractionStatus.NEEDS_REVIEW.value: ParseStatus.NEEDS_REVIEW.value,
    ExtractionStatus.FAILED.value: ParseStatus.FAILED.value,
}


def image_hash(data: bytes, file_type: str) -> str | None:
    if file_type == "pdf":
        return None  # PDFs of one template look alike at any resolution: they are matched by SHA-256
    with Image.open(io.BytesIO(data)) as image:
        return phash(image)


async def store_claim_document(
    session: AsyncSession, storage: Storage, claim_id: str, file_name: str, file_type: str, data: bytes
) -> Document:
    document = Document(
        claim_id=claim_id,
        storage_key="",
        sha256=hashlib.sha256(data).hexdigest(),
        phash=await asyncio.to_thread(image_hash, data, file_type),
        page_count=await asyncio.to_thread(page_count, data, file_type),
        file_name=file_name,
        file_type=file_type,
        size_bytes=len(data),
        parse_status=ParseStatus.PENDING.value,
        issues=[],
    )
    session.add(document)
    await session.flush()
    name = f"claims/{claim_id}/docs/{document.id}.{EXTENSIONS[file_type]}"
    document.storage_key = await asyncio.to_thread(storage.upload, name, data, FILE_TYPES[file_type])
    await session.commit()
    await session.refresh(document)
    return document


async def store_extraction(
    session: AsyncSession, document: Document, result: ExtractionResult, model: str
) -> DocumentExtraction:
    version = (
        await session.scalar(
            select(func.max(DocumentExtraction.version)).where(DocumentExtraction.document_id == document.id)
        )
        or 0
    ) + 1
    extraction = DocumentExtraction(
        document_id=document.id,
        version=version,
        doc_type=result.doc_type,
        schema_version=SCHEMA_VERSION,
        model=model,
        prompt_version=PROMPT_VERSION,
        status=result.status,
        route=result.route,
        attempts=result.attempts,
        validation_errors=result.validation_errors or None,
        classification_confidence=round(result.classification_confidence, 3)
        if result.classification_confidence is not None
        else None,
        error=result.error,
        source_text=result.source_text,
        generated_by=GeneratedBy.AI.value,
    )
    session.add(extraction)
    await session.flush()
    fields = [
        {
            "extraction_id": extraction.extraction_id,
            "field_path": f.field_path,
            "value_text": f.value_text,
            "value_normalised": f.value_normalised,
            "page": f.page,
            "bbox": f.bbox,
            "source_quote": f.source_quote,
            "provenance_status": f.provenance_status,
            "confidence": f.confidence,
        }
        for f in result.fields
    ]
    lines = [
        {
            "extraction_id": extraction.extraction_id,
            "line_no": ln.line_no,
            "description": ln.description,
            "service_code": (ln.service_code or "")[:20] or None,
            "service_date": date.fromisoformat(ln.service_date) if ln.service_date else None,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "amount": ln.amount,
            "page": ln.page,
            "bbox": ln.bbox,
        }
        for ln in result.lines
    ]
    if fields:
        await session.execute(insert(ExtractedField.__table__), fields)
    if lines:
        await session.execute(insert(ExtractedLine.__table__), lines)
    document.doc_type = result.doc_type
    document.parse_status = PARSE_STATUS[result.status]
    verified = sum(1 for f in result.fields if f.provenance_status == "verified" and f.value_text is not None)
    filled = sum(1 for f in result.fields if f.value_text is not None)
    await write_events(
        session,
        [
            event(
                EventType.EXTRACTION_CREATED,
                "document_extraction",
                extraction.extraction_id,
                claim_id=document.claim_id,
                actor_type=ActorType.AI,
                model=model,
                prompt_version=PROMPT_VERSION,
                document_id=document.id,
                version=version,
                doc_type=result.doc_type,
                status=result.status,
                route=result.route,
                fields=filled,
                verified_fields=verified,
            )
        ],
    )
    return extraction


async def extract_and_store(
    session: AsyncSession, storage: Storage, reader: Reader, document: Document, doc_type: str | None = None
) -> DocumentExtraction:
    data = await asyncio.to_thread(storage.download, document.storage_key.removeprefix(storage.key("")))
    parsed = await asyncio.to_thread(parse_items, data) if document.file_type == "pdf" else None
    result = await extract_document(reader, parsed, data, document.file_type, doc_type)
    return await store_extraction(session, document, result, reader.model)


async def process_claim_document(
    database: Database, storage: Storage, reader: Reader, settings: Settings, document_id: int, doc_type: str | None
) -> None:
    """Background task: extract one document (and, from there, compare it with its claim)."""
    async with database.sessionmaker() as session:
        document = await session.get(Document, document_id)
        if document is None:  # pragma: no cover
            return
        try:
            await extract_and_store(session, storage, reader, document, doc_type)
            await session.commit()
            # Compare the claim with its documents, and relate claims that share this document.
            if document.claim_id:
                await compare_claim(session, reader, settings, document.claim_id)
                await build_graph(session, settings, claim_ids=[document.claim_id])
                await session.commit()
        except Exception as exc:
            log.exception("claim_document_failed", document_id=document_id)
            await session.rollback()
            document = await session.get(Document, document_id)
            if document is not None:
                document.parse_status = ParseStatus.FAILED.value
                document.issues = [*(document.issues or []), f"Processing failed: {type(exc).__name__}"]
                await session.commit()


async def latest_extraction(
    session: AsyncSession, document_id: int, version: int | None = None
) -> DocumentExtraction | None:
    query = select(DocumentExtraction).where(DocumentExtraction.document_id == document_id)
    if version is not None:
        query = query.where(DocumentExtraction.version == version)
    return await session.scalar(query.order_by(DocumentExtraction.version.desc()).limit(1))
