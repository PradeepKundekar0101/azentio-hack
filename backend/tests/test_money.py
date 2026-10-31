from decimal import Decimal

import pytest

from app.core.money import AmountError, inr, parse_amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,42,000.50", Decimal("142000.50")),
        ("142000.5", Decimal("142000.5")),
        ("₹1,42,000", Decimal("142000")),
        ("₹ 1,42,000.00", Decimal("142000.00")),
        ("  7,000  ", Decimal("7000")),
        ("1,000", Decimal("1000")),
        ("12,34,56,789.05", Decimal("123456789.05")),
        ("0", Decimal("0")),
        ("-500", Decimal("-500")),
    ],
)
def test_parse_amount_accepts_indian_and_plain_formats(text: str, expected: Decimal) -> None:
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text",
    ["1.42.000", "142,000", "1,4,2000", "12.345", "abc", "", "₹", "Rs 500", "1e5", "5,00"],
)
def test_parse_amount_rejects_other_formats(text: str) -> None:
    with pytest.raises(AmountError):
        parse_amount(text)


def test_parse_amount_accepts_numbers_from_json() -> None:
    assert parse_amount(142000) == Decimal("142000")
    assert parse_amount(142000.5) == Decimal("142000.5")
    assert parse_amount(Decimal("7000.25")) == Decimal("7000.25")


def test_parse_amount_rejects_bool_and_non_finite_numbers() -> None:
    for value in (True, float("nan"), float("inf")):
        with pytest.raises(AmountError):
            parse_amount(value)


@pytest.mark.parametrize(
    ("value", "paise", "expected"),
    [
        (Decimal("142000"), True, "₹1,42,000.00"),
        (Decimal("142000.5"), None, "₹1,42,000.50"),
        (Decimal("142000"), None, "₹1,42,000"),
        (Decimal("6000"), None, "₹6,000"),
        (Decimal("999"), True, "₹999.00"),
        (Decimal("-8400"), None, "-₹8,400"),
        (Decimal("12345678.905"), True, "₹1,23,45,678.91"),
    ],
)
def test_inr_formats_in_indian_grouping(value: Decimal, paise: bool | None, expected: str) -> None:
    assert inr(value, paise=paise) == expected
