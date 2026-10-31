"""Docling parsing (tables and page numbers kept), file-type sniffing, and page rendering for the vision route."""

import io
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import pypdfium2 as pdfium
from PIL import Image

# Pages with less extractable text than this (and every image) go to Claude vision instead.
VISION_MIN_CHARS = 200
RENDER_DPI = 200

_converter = None
_lock = Lock()

FILE_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}


def sniff_type(data: bytes) -> str | None:
    """The real file type from its bytes: pdf, png or jpeg (None for anything else)."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


@dataclass
class ParsedPage:
    number: int
    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)

    @property
    def needs_vision(self) -> bool:
        return len(self.text.strip()) < VISION_MIN_CHARS


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]

    @property
    def text(self) -> str:
        return "\n\n".join(f"--- page {p.number} ---\n{p.text}" for p in self.pages)


def _get_converter():  # noqa: ANN202 - Docling types are imported lazily (the import is slow)
    global _converter
    with _lock:
        if _converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            # No OCR: scanned pages go to the vision model. Table structure on, for line items.
            # Models baked into the Docker image (DOCLING_ARTIFACTS_PATH); unset locally, so they download once.
            artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH") or None
            options = PdfPipelineOptions(do_ocr=False, do_table_structure=True, artifacts_path=artifacts)
            _converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    return _converter


def parse_pdf(data: bytes) -> ParsedDocument:
    from docling_core.types.doc import TableItem, TextItem

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(data)
        handle.flush()
        document = _get_converter().convert(Path(handle.name)).document
    pages: dict[int, ParsedPage] = {number: ParsedPage(number) for number in (document.pages or {})}
    for item, _level in document.iterate_items():
        provenance = item.prov[0] if getattr(item, "prov", None) else None
        number = provenance.page_no if provenance else 1
        page = pages.setdefault(number, ParsedPage(number))
        if isinstance(item, TableItem):
            rows: dict[int, list] = {}
            for cell in item.data.table_cells:
                rows.setdefault(cell.start_row_offset_idx, []).append(cell)
            page.tables.append(
                [
                    [c.text.strip() for c in sorted(cells, key=lambda c: c.start_col_offset_idx)]
                    for _, cells in sorted(rows.items())
                ]
            )
            page.text += "\n" + item.export_to_markdown(doc=document) + "\n"
        elif isinstance(item, TextItem):
            page.text += item.text + "\n"
    if not pages:
        pages[1] = ParsedPage(1)
    return ParsedDocument([pages[k] for k in sorted(pages)])


def page_count(data: bytes, file_type: str) -> int:
    return len(pdfium.PdfDocument(data)) if file_type == "pdf" else 1


def render_page(data: bytes, file_type: str, page: int = 1, dpi: int = RENDER_DPI) -> bytes:
    """PNG bytes of one page: PDFs rendered with pypdfium2, images passed through as PNG."""
    if file_type == "pdf":
        image = pdfium.PdfDocument(data)[page - 1].render(scale=dpi / 72).to_pil()
    else:
        image = Image.open(io.BytesIO(data))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class ItemPage:
    number: int
    width: float
    height: float
    spans: list[Any] = field(default_factory=list)  # provenance.TextSpan

    @property
    def text(self) -> str:
        return "\n".join(span.text for span in self.spans)

    @property
    def needs_vision(self) -> bool:
        return len(self.text.strip()) < VISION_MIN_CHARS


@dataclass
class ItemDocument:
    """Every text item and table cell Docling found, with its page and its box as fractions of the page
    (top-left origin), so a value can be traced to the place it was printed."""

    pages: list[ItemPage]

    @property
    def text(self) -> str:
        return "\n\n".join(f"--- page {p.number} ---\n{p.text}" for p in self.pages)

    @property
    def spans(self) -> list[Any]:
        return [span for page in self.pages for span in page.spans]


def _fraction_box(bbox: Any, width: float, height: float) -> dict[str, float]:
    box = bbox.to_top_left_origin(page_height=height)
    return {
        "l": round(box.l / width, 4),
        "t": round(box.t / height, 4),
        "r": round(box.r / width, 4),
        "b": round(box.b / height, 4),
    }


def parse_items(data: bytes) -> ItemDocument:
    from docling_core.types.doc import TableItem, TextItem

    from app.documents.provenance import TextSpan

    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(data)
        handle.flush()
        document = _get_converter().convert(Path(handle.name)).document
    pages = {
        number: ItemPage(number, page.size.width, page.size.height) for number, page in (document.pages or {}).items()
    }
    for item, _level in document.iterate_items():
        provenance = item.prov[0] if getattr(item, "prov", None) else None
        if provenance is None:
            continue
        page = pages.get(provenance.page_no)
        if page is None:
            continue
        if isinstance(item, TableItem):
            for cell in item.data.table_cells:
                if cell.text.strip() and cell.bbox is not None:
                    box = _fraction_box(cell.bbox, page.width, page.height)
                    page.spans.append(TextSpan(page.number, cell.text.strip(), box))
        elif isinstance(item, TextItem) and item.text.strip():
            page.spans.append(
                TextSpan(page.number, item.text.strip(), _fraction_box(provenance.bbox, page.width, page.height))
            )
    if not pages:
        pages[1] = ItemPage(1, 1.0, 1.0)
    return ItemDocument([pages[k] for k in sorted(pages)])
