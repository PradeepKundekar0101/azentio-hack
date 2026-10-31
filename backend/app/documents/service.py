"""Document lifecycle: upload → parse and extract (background) → review draft → confirm through Phase 2 validation."""

import asyncio
import hashlib
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import BatchStatus, ClaimSource, ParseStatus
from app.core.logging import get_logger
from app.db.models import Claim, Document, ImportBatch, Provider, ServiceCode
from app.db.session import Database
from app.documents.extract import Extractor, extract_invoice
from app.documents.mapping import ProviderRef, ServiceRef, draft_claim
from app.documents.parse import FILE_TYPES, parse_pdf
from app.ingest.commit import commit_rows
from app.ingest.mapping import Dataset
from app.ingest.readers import RawRow, RawTable
from app.ingest.service import load_existing
from app.ingest.validate import ValidationResult, validate_tables
from app.storage.spaces import Storage

log = get_logger(__name__)


async def store_document(
    session: AsyncSession, storage: Storage, file_name: str, file_type: str, data: bytes
) -> Document:
    sha = hashlib.sha256(data).hexdigest()
    document = Document(
        storage_key="",
        sha256=sha,
        file_name=file_name,
        file_type=file_type,
        size_bytes=len(data),
        parse_status=ParseStatus.PENDING.value,
    )
    session.add(document)
    await session.flush()
    document.storage_key = await asyncio.to_thread(
        storage.upload,
        f"documents/{document.id}.{'jpg' if file_type == 'jpeg' else file_type}",
        data,
        FILE_TYPES[file_type],
    )
    earlier = await session.scalar(
        select(Document).where(Document.sha256 == sha, Document.id != document.id).order_by(Document.id).limit(1)
    )
    document.issues = (
        [
            f"This exact file was uploaded before as document {earlier.id}"
            + (f" (claim {earlier.claim_id})." if earlier.claim_id else ".")
        ]
        if earlier
        else []
    )
    await session.commit()
    await session.refresh(document)
    return document


async def _references(session: AsyncSession) -> tuple[list[ProviderRef], list[ServiceRef]]:
    providers = [ProviderRef(p.provider_id, p.name) for p in await session.scalars(select(Provider))]
    services = [ServiceRef(s.code, s.description, s.category) for s in await session.scalars(select(ServiceCode))]
    return providers, services


async def process_document(database: Database, storage: Storage, extractor: Extractor, document_id: int) -> None:
    async with database.sessionmaker() as session:
        document = await session.get(Document, document_id)
        if document is None:  # pragma: no cover
            return
        try:
            data = await asyncio.to_thread(storage.download, document.storage_key.removeprefix(storage.key("")))
            parsed = await asyncio.to_thread(parse_pdf, data) if document.file_type == "pdf" else None
            extraction = await extract_invoice(extractor, parsed, data, document.file_type)
            providers, services = await _references(session)
            draft = draft_claim(extraction.data, providers, services) if extraction.data else None
            document.extracted = {
                "route": extraction.route,
                "attempts": extraction.attempts,
                "extraction": extraction.data.model_dump() if extraction.data else None,
                "draft": draft,
            }
            document.issues = [*(document.issues or [])[:1], *extraction.problems]
            if extraction.data is None:
                document.parse_status = ParseStatus.FAILED.value
            else:
                document.parse_status = (
                    ParseStatus.NEEDS_REVIEW if extraction.problems else ParseStatus.EXTRACTED
                ).value
            resolved = [ln for ln in (draft or {}).get("lines", []) if ln["service_code"]]
            total = len((draft or {}).get("lines", [])) or 1
            document.confidence = Decimal(len(resolved)) / Decimal(total) if draft else None
        except Exception as exc:
            log.exception("document_processing_failed", document_id=document_id)
            document.parse_status = ParseStatus.FAILED.value
            document.issues = [*(document.issues or []), f"Processing failed: {type(exc).__name__}"]
        await session.commit()


def confirm_tables(document: Document, claim_id: str, form: dict[str, Any]) -> list[RawTable]:
    """The reviewed form as raw rows, so it runs through exactly the same validation as a file import."""
    claim = {**form["claim"], "claim_id": claim_id, "status": "open"}
    claims = RawTable(document.file_name, None, Dataset.CLAIMS, list(claim), [RawRow(1, claim)])
    lines = []
    for n, line in enumerate(form["lines"], start=1):
        row = {
            "line_id": f"{claim_id}-L{n:02d}",
            "claim_id": claim_id,
            "invoice_reference": form.get("invoice_reference"),
            "provider_id": form.get("provider_id"),
            "provider_name": form.get("provider_name"),
            **{
                k: line.get(k)
                for k in (
                    "service_date",
                    "service_code",
                    "service_description",
                    "category",
                    "quantity",
                    "unit_price",
                    "line_amount",
                )
            },
        }
        lines.append(RawRow(n + 1, row))
    headers = list(lines[0].values) if lines else []
    return [claims, RawTable(document.file_name, None, Dataset.LINE_ITEMS, headers, lines)]


DOCUMENT_CLAIM_BASE = 800000  # imports and the generated samples use other ranges


async def _free_claim_id(session: AsyncSession, document_id: int) -> str:
    """CLM-8xxxxx from the document number; skips forward if an import already used that ID."""
    number = DOCUMENT_CLAIM_BASE + document_id
    while await session.get(Claim, f"CLM-{number:06d}") is not None:
        number += 1000
    return f"CLM-{number:06d}"


async def confirm_document(
    session: AsyncSession, document: Document, form: dict[str, Any], username: str, today: date | None = None
) -> tuple[ValidationResult, ImportBatch | None, str]:
    claim_id = await _free_claim_id(session, document.id)
    tables = confirm_tables(document, claim_id, form)
    existing = await load_existing(session, tables)
    result = validate_tables(tables, existing, today or date.today())
    if any(not row.ok for rows in result.rows.values() for row in rows):
        return result, None, claim_id
    batch = ImportBatch(
        uploaded_by=username,
        files=[
            {
                "file_name": document.file_name,
                "storage_key": document.storage_key,
                "size": document.size_bytes,
                "content_type": FILE_TYPES[document.file_type],
                "datasets": ["claims", "line_items"],
            }
        ],
        status=BatchStatus.COMPLETED.value,
        counts=result.counts(),
    )
    session.add(batch)
    await session.flush()
    await commit_rows(session, result, batch.id, ClaimSource.DOCUMENT)
    document.claim_id = claim_id
    document.parse_status = ParseStatus.CONFIRMED.value
    await session.commit()
    return result, batch, claim_id


def settings_extractor(settings: Settings) -> Extractor:
    return Extractor(settings)
