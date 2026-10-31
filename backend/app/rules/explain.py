"""Plain-language explanations, filled only from the values a check used."""

from datetime import date
from decimal import Decimal

from app.core.money import inr
from app.rules.context import RuleData


def d(value: date) -> str:
    return value.strftime("%-d %b %Y")


def qty(value: Decimal) -> str:
    text = f"{value.normalize():f}"
    return text


def days(value: Decimal) -> str:
    return f"{qty(value)} day" + ("" if value == 1 else "s")


def per_day_excess(rule: RuleData, rate: Decimal, count: Decimal, excess: Decimal, what: str) -> str:
    limit = rule.limit_amount or Decimal(0)
    return (
        f"{what} {inr(rate)}/day exceeds the {inr(limit)}/day limit ({rule.label}) for {days(count)}: "
        f"({inr(rate)} − {inr(limit)}) × {qty(count)} = {inr(excess)}."
    )


def per_day_formula(rule: RuleData, rate: Decimal, count: Decimal, excess: Decimal) -> str:
    return f"({inr(rate)} − {inr(rule.limit_amount or 0)}) × {qty(count)} days = {inr(excess)}"


def scope_name(rule: RuleData) -> str:
    return rule.scope_value.replace("_", " ")
