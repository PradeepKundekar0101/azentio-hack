"""Rupee amounts as Decimal: strict parsing of Indian and plain formats, and Indian-style formatting."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0")

# Plain digits ("142000") or Indian grouping ("1,42,000"), optional sign, up to two decimals, optional ₹.
_AMOUNT = re.compile(r"^(?P<sign>-)?₹?\s*(?P<int>\d+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.(?P<frac>\d{1,2}))?$")


class AmountError(ValueError):
    """Raised when a value is not an accepted rupee amount."""


def parse_amount(value: str | int | float | Decimal) -> Decimal:
    """Parse '1,42,000.50', '142000.5' or '₹1,42,000' (and JSON numbers) to Decimal; reject anything else."""
    if isinstance(value, bool):
        raise AmountError(f"not an amount: {value!r}")
    if isinstance(value, Decimal | int):
        result = Decimal(value)
    elif isinstance(value, float):
        # repr gives the shortest string that round-trips, so 142000.5 stays 142000.5.
        result = Decimal(repr(value))
    else:
        match = _AMOUNT.match(value.strip())
        if match is None:
            raise AmountError(f"not an accepted amount format: {value!r}")
        digits = match["int"].replace(",", "")
        frac = f".{match['frac']}" if match["frac"] else ""
        result = Decimal(f"{match['sign'] or ''}{digits}{frac}")
    if not result.is_finite():
        raise AmountError(f"not a finite amount: {value!r}")
    if result.as_tuple().exponent < -2:  # type: ignore[operator]
        raise AmountError(f"more than two decimal places: {value!r}")
    return result


def q2(value: Decimal) -> Decimal:
    """Round to paise, half up."""
    try:
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise AmountError(f"cannot round {value!r}") from exc


def _group_indian(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join(pairs) + "," + tail


def inr(value: Decimal | int | str, paise: bool | None = None) -> str:
    """₹1,42,000.00 with paise=True; by default paise are shown only when non-zero (₹6,000, ₹1,42,000.50)."""
    amount = q2(Decimal(value))
    sign = "-" if amount < 0 else ""
    rupees, cents = f"{abs(amount):.2f}".split(".")
    show_paise = paise if paise is not None else cents != "00"
    return f"{sign}₹{_group_indian(rupees)}" + (f".{cents}" if show_paise else "")
