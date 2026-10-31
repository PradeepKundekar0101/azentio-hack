"""Match claim lines to document lines: a similarity per pair, then one-to-one assignment (Hungarian algorithm).

Similarity = 0.40 × same service code + 0.30 × description similarity (token set ratio) + 0.20 × amount closeness
+ 0.10 × same service date. Pairs at 0.60 or above are matched; pairs between 0.40 and 0.60 that are left over are
candidates the model may confirm.
"""

from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
from rapidfuzz import fuzz, utils
from scipy.optimize import linear_sum_assignment

from app.documents.compare import ClaimLineView, DocLineView

ACCEPT = 0.60
CANDIDATE = 0.40


@dataclass
class Pair:
    claim: ClaimLineView
    doc: DocLineView
    score: float
    generated_by: str = "rule"
    confidence: float | None = None


@dataclass
class Assignment:
    pairs: list[Pair] = field(default_factory=list)
    candidates: list[Pair] = field(default_factory=list)
    unmatched_claim: list[ClaimLineView] = field(default_factory=list)
    unmatched_document: list[DocLineView] = field(default_factory=list)


def description_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a, b, processor=utils.default_process) / 100


def amount_closeness(a: Decimal | None, b: Decimal | None) -> float:
    if a is None or b is None:
        return 0.0
    high = max(abs(a), abs(b))
    if high == 0:
        return 1.0
    return max(0.0, 1.0 - float(abs(a - b) / high))


def similarity(claim: ClaimLineView, doc: DocLineView) -> float:
    code = 1.0 if doc.service_code and doc.service_code == claim.service_code else 0.0
    same_day = 1.0 if doc.service_date is not None and doc.service_date == claim.service_date else 0.0
    return round(
        0.40 * code
        + 0.30 * description_similarity(claim.description, doc.description)
        + 0.20 * amount_closeness(claim.amount, doc.amount)
        + 0.10 * same_day,
        4,
    )


def assign_lines(claim_lines: list[ClaimLineView], doc_lines: list[DocLineView]) -> Assignment:
    result = Assignment()
    if not claim_lines or not doc_lines:
        return Assignment(unmatched_claim=list(claim_lines), unmatched_document=list(doc_lines))
    scores = np.array([[similarity(c, d) for d in doc_lines] for c in claim_lines])
    rows, cols = linear_sum_assignment(-scores)
    used_claim, used_doc = set(), set()
    for r, c in zip(rows, cols, strict=True):
        score = float(scores[r, c])
        if score >= ACCEPT:
            result.pairs.append(Pair(claim_lines[r], doc_lines[c], score))
            used_claim.add(r)
            used_doc.add(c)
    # Left-over lines: the best remaining borderline pair for each claim line, if any, goes to the model.
    free_docs = [c for c in range(len(doc_lines)) if c not in used_doc]
    for r in range(len(claim_lines)):
        if r in used_claim or not free_docs:
            continue
        best = max(free_docs, key=lambda c: scores[r, c])
        if CANDIDATE <= scores[r, best] < ACCEPT:
            result.candidates.append(Pair(claim_lines[r], doc_lines[best], float(scores[r, best])))
            free_docs.remove(best)
            used_claim.add(r)
            used_doc.add(best)
    result.unmatched_claim = [c for r, c in enumerate(claim_lines) if r not in used_claim]
    result.unmatched_document = [d for c, d in enumerate(doc_lines) if c not in used_doc]
    return result
