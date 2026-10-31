"""Stable finding IDs for alerts: the same finding gets the same ID on every run, so decisions can reference it."""

import hashlib


def alert_finding_id(
    claim_id: str, category: str, line_id: str | None, pattern: str, rule_id: str | None, matched: str | None
) -> str:
    key = "|".join((claim_id, category, line_id or "", pattern, rule_id or "", matched or ""))
    return f"ALR-{hashlib.sha256(key.encode()).hexdigest()[:12].upper()}"
