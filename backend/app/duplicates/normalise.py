"""Normalised references for duplicate checks: INV-00452, inv 452 and INV452 all become INV452."""

import re

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_LEADING_ZEROS = re.compile(r"(?<![0-9])0+(?=[0-9])")


def normalise_reference(value: str | None) -> str | None:
    """Uppercase, drop spaces and punctuation, strip leading zeros from each numeric run."""
    if value is None:
        return None
    text = _LEADING_ZEROS.sub("", _NON_ALNUM.sub("", value.upper()))
    return text or None
