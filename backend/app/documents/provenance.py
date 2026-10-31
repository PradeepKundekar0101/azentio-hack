"""Provenance check: find each value's source quote among the document's text items.

The quote is looked for on its stated page first, then on the others, after normalising whitespace and case; OCR
noise is allowed down to a fuzzy score of 90. Found means verified, with that item's box. Not found means
unverified, and the value is never used to compute money, so an invented value cannot enter the analysis. Pages
read only by vision have no text items: their values are page_only (usable, but any amount they produce is an
estimate).
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from rapidfuzz import fuzz

FUZZY_MIN = 90
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class TextSpan:
    page: int
    text: str
    bbox: dict[str, float]


@dataclass(frozen=True)
class Located:
    status: str  # verified, unverified or page_only
    page: int | None
    bbox: dict[str, float] | None
    confidence: Decimal


def normalise(text: str) -> str:
    return _SPACE.sub(" ", text).strip().casefold()


def _score(quote: str, span: str) -> float:
    if quote in span:
        return 100.0
    if len(span) < len(quote) * 0.6:  # a short item cannot hold a long quote
        return 0.0
    return fuzz.partial_ratio(quote, span)


MAX_RUN = 3


def _runs(spans: list[TextSpan]) -> list[list[TextSpan]]:
    """Consecutive items of one page (in reading order), two and three at a time."""
    runs = []
    for size in range(2, MAX_RUN + 1):
        for i in range(len(spans) - size + 1):
            run = spans[i : i + size]
            if len({span.page for span in run}) == 1:
                runs.append(run)
    return runs


def _union(boxes: list[dict[str, float]]) -> dict[str, float]:
    return {
        "l": min(b["l"] for b in boxes),
        "t": min(b["t"] for b in boxes),
        "r": max(b["r"] for b in boxes),
        "b": max(b["b"] for b in boxes),
    }


def locate(quote: str | None, page: int | None, spans: list[TextSpan], vision_pages: set[int]) -> Located:
    if page is not None and page in vision_pages:
        return Located("page_only", page, None, Decimal("0.500"))
    target = normalise(quote or "")
    if not target:
        return Located("unverified", page, None, Decimal("0.000"))
    ordered = sorted(spans, key=lambda s: (s.page != page, s.page))
    best: tuple[float, TextSpan] | None = None
    for span in ordered:
        score = _score(target, normalise(span.text))
        if score == 100.0:
            return Located("verified", span.page, span.bbox, Decimal("1.000"))
        if best is None or score > best[0]:
            best = (score, span)
    if best is not None and best[0] >= FUZZY_MIN:
        return Located("verified", best[1].page, best[1].bbox, Decimal(str(round(best[0] / 100, 3))))
    # A quote across neighbouring items ("Total (Rs)" and "752.00" are two items): runs of up to three in a row.
    for run in _runs(ordered):
        if target in normalise(" ".join(span.text for span in run)):
            return Located("verified", run[0].page, _union([span.bbox for span in run]), Decimal("0.950"))
    if not spans and vision_pages:
        return Located("page_only", page or min(vision_pages), None, Decimal("0.500"))
    return Located("unverified", page, None, Decimal("0.000"))
