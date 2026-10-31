"""Normalise extracted values with the same parsers as file imports, then check them: for invoices, line quantity ×
unit price = amount, lines add up to the subtotal and subtotal + taxes = total (within Rs 1); for discharge summaries,
discharge on or after admission. Every check is code; the model only reads."""

from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.core.money import AmountError, inr, parse_amount, q2
from app.documents.schemas import DischargeSummaryDocument, InvoiceDocument, RepairEstimateDocument
from app.ingest.schemas import DateError, parse_date

TOLERANCE = Decimal("1.00")
AMOUNT_FIELDS = {"unit_price", "amount", "subtotal", "taxes", "total"}
QUANTITY_FIELDS = {"quantity"}


def kind_of(name: str) -> str:
    if name in AMOUNT_FIELDS:
        return "amount"
    if name in QUANTITY_FIELDS:
        return "quantity"
    if name.endswith("_date"):
        return "date"
    return "text"


def normalise_value(name: str, text: str | None) -> str | None:
    """Canonical text for a value (ISO dates, plain decimals), or None when it is missing or cannot be parsed."""
    if text is None or not text.strip():
        return None
    kind = kind_of(name)
    try:
        if kind == "amount":
            return f"{q2(parse_amount(text)):.2f}"
        if kind == "quantity":
            return f"{Decimal(text.replace(',', '').strip()).normalize():f}"
        if kind == "date":
            return parse_date(text).isoformat()
    except (AmountError, DateError, InvalidOperation, ValueError):
        return None
    return " ".join(text.split())


def _amount(text: str | None) -> Decimal | None:
    value = normalise_value("amount", text)
    return Decimal(value) if value is not None else None


def _quantity(text: str | None) -> Decimal | None:
    value = normalise_value("quantity", text)
    return Decimal(value) if value is not None else None


def _date(text: str | None) -> date | None:
    value = normalise_value("x_date", text)
    return date.fromisoformat(value) if value is not None else None


def _check_dates(model: BaseModel, errors: list[str]) -> None:
    for name, value in model:
        if name.endswith("_date") and getattr(value, "value", None) and _date(value.value) is None:
            errors.append(f"{name.replace('_', ' ').capitalize()} '{value.value}' is not a valid date.")


def _check_lines(lines: list, errors: list[str]) -> Decimal:
    total = Decimal(0)
    for n, line in enumerate(lines, start=1):
        quantity, price, amount = (
            _quantity(line.quantity.value),
            _amount(line.unit_price.value),
            _amount(line.amount.value),
        )
        if amount is None:
            errors.append(f"Line {n}: the amount '{line.amount.value}' is missing or not a number.")
            continue
        total += amount
        if quantity is not None and price is not None and abs(q2(quantity * price) - amount) > TOLERANCE:
            errors.append(
                f"Line {n}: {line.quantity.value} × {line.unit_price.value} does not equal {line.amount.value}."
            )
        date_field = getattr(line, "service_date", None)
        if date_field is not None and date_field.value and _date(date_field.value) is None:
            errors.append(f"Line {n}: service date '{date_field.value}' is not a valid date.")
    return total


def validate_extraction(model: BaseModel) -> list[str]:
    errors: list[str] = []
    _check_dates(model, errors)
    if isinstance(model, InvoiceDocument | RepairEstimateDocument):
        if not model.lines:
            errors.append("No line items were found.")
        line_sum = _check_lines(model.lines, errors)
        total = _amount(model.total.value)
        if total is None:
            errors.append("The total was not found.")
        if isinstance(model, InvoiceDocument):
            subtotal, taxes = _amount(model.subtotal.value), _amount(model.taxes.value) or Decimal(0)
            if subtotal is not None:
                if model.lines and abs(line_sum - subtotal) > TOLERANCE:
                    errors.append(f"Lines add up to {inr(line_sum)}, but the subtotal is {inr(subtotal)}.")
                if total is not None and abs(subtotal + taxes - total) > TOLERANCE:
                    errors.append(
                        f"Subtotal {inr(subtotal)} + taxes {inr(taxes)} does not equal the total {inr(total)}."
                    )
            elif total is not None and model.lines and abs(line_sum + taxes - total) > TOLERANCE:
                errors.append(f"Lines add up to {inr(line_sum)}, but the total is {inr(total)}.")
        elif total is not None and model.lines and abs(line_sum - total) > TOLERANCE:
            errors.append(f"Lines add up to {inr(line_sum)}, but the total is {inr(total)}.")
    if isinstance(model, DischargeSummaryDocument):
        admitted, discharged = _date(model.admission_date.value), _date(model.discharge_date.value)
        if admitted and discharged and discharged < admitted:
            errors.append(f"Discharge ({discharged:%d %b %Y}) is before admission ({admitted:%d %b %Y}).")
        if not model.patient_name.value:
            errors.append("The patient name was not found.")
    return errors
