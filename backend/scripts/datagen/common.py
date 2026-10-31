"""Shared constants and helpers: dates, money, invoice-reference normalisation and reference data."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache

from rapidfuzz import fuzz

from app.core.money import q2
from scripts.seed_reference import load_reference_rows

TODAY = date(2026, 10, 31)
ZERO = Decimal("0")
DATASETS = ("policies", "policy_rules", "claims", "line_items", "settlements")
ID_FIELDS = {
    "policies": "policy_number",
    "policy_rules": "rule_id",
    "claims": "claim_id",
    "line_items": "line_id",
    "settlements": "settlement_id",
}
CLAIM_TYPES = ("inpatient", "outpatient", "daycare", "pharmacy", "diagnostics")
CATEGORIES = (
    "room",
    "icu",
    "consultation",
    "procedure",
    "pharmacy",
    "diagnostics",
    "consumables",
    "physiotherapy",
    "other",
)

# Near-duplicate score weights and threshold from the plan (Phase 4).
NEAR_DUPLICATE_THRESHOLD = 0.80
LEGIT_REF_SIMILARITY_MAX = 0.90


def percent_of(amount: Decimal, percent: int | Decimal) -> Decimal:
    return q2(amount * Decimal(percent) / Decimal(100))


_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_LEADING_ZEROS = re.compile(r"(?<![0-9])0+(?=[0-9])")


def norm_ref(value: str | None) -> str:
    """Uppercase, drop non-alphanumerics, strip leading zeros of the numeric part: INV-00452 -> INV452."""
    if not value:
        return ""
    return _LEADING_ZEROS.sub("", _NON_ALNUM.sub("", value.upper()))


def ref_similarity(a: str, b: str) -> float:
    """rapidfuzz ratio on normalised references, 0-1."""
    return fuzz.ratio(norm_ref(a), norm_ref(b)) / 100.0


def near_score(similarity: float, gap_days: int, amount_diff: float, jaccard: float) -> float:
    return (
        0.35 * similarity
        + 0.25 * (1 - min(gap_days, 7) / 7)
        + 0.25 * (1 - min(amount_diff, 0.10) / 0.10)
        + 0.15 * jaccard
    )


@dataclass(frozen=True)
class ServiceCode:
    code: str
    description: str
    category: str
    repeatable: bool
    min_interval_days: int | None
    max_per_week: int | None


@dataclass(frozen=True)
class Provider:
    provider_id: str
    name: str
    city: str


@cache
def service_codes() -> dict[str, ServiceCode]:
    rows, _ = load_reference_rows()
    return {row["code"]: ServiceCode(**row) for row in rows}


@cache
def providers() -> tuple[Provider, ...]:
    _, rows = load_reference_rows()
    return tuple(Provider(row["provider_id"], row["name"], row["city"]) for row in rows)


# ---- dates -----------------------------------------------------------------------------------------------

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})([-/])(\d{1,2})\2(\d{4})$")
_TWO_DIGIT_YEAR = re.compile(r"^\d{1,2}[-/.]\d{1,2}[-/.]\d{2}$")


def parse_date(value: str) -> tuple[date | None, str | None]:
    """Parse an accepted date; return (date, None) or (None, 'ambiguous_date' | 'invalid_date')."""
    text = value.strip()
    if _TWO_DIGIT_YEAR.match(text):
        return None, "ambiguous_date"
    try:
        if match := _ISO.match(text):
            return date(int(match[1]), int(match[2]), int(match[3])), None
        if match := _DMY.match(text):
            return date(int(match[4]), int(match[3]), int(match[1])), None
    except ValueError:
        return None, "invalid_date"
    return None, "invalid_date"
