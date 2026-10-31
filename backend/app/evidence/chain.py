"""Hash chain over a claim's evidence history.

Every entry's hash covers its own fields and the previous entry's hash, so editing or deleting any stored
entry changes every hash after it. `verify` recomputes the chain from the stored rows.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.db.models import EvidenceEvent


def to_json(value: Any) -> Any:
    """Plain JSON values only (Decimals, dates and enums become strings), so the stored JSONB hashes the
    same after a round trip through the database."""
    return json.loads(json.dumps(value, default=str))


def _timestamp(at: datetime) -> str:
    return at.astimezone(UTC).isoformat(timespec="microseconds")


def entry_hash(
    *,
    claim_id: str,
    seq: int,
    at: datetime,
    actor: str,
    actor_role: str | None,
    kind: str,
    finding_key: str | None,
    alert_id: int | None,
    summary: str,
    payload: Any,
    prev_hash: str | None,
) -> str:
    body = {
        "claim_id": claim_id,
        "seq": seq,
        "at": _timestamp(at),
        "actor": actor,
        "actor_role": actor_role,
        "kind": kind,
        "finding_key": finding_key,
        "alert_id": alert_id,
        "summary": summary,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_of(event: EvidenceEvent) -> str:
    return entry_hash(
        claim_id=event.claim_id,
        seq=event.seq,
        at=event.at,
        actor=event.actor,
        actor_role=event.actor_role,
        kind=event.kind,
        finding_key=event.finding_key,
        alert_id=event.alert_id,
        summary=event.summary,
        payload=event.payload,
        prev_hash=event.prev_hash,
    )


@dataclass(frozen=True)
class Verification:
    verified: bool
    events: int
    head_hash: str | None
    broken_at: int | None = None
    reason: str | None = None


def verify(events: list[EvidenceEvent], head_hash: str | None) -> Verification:
    """Events in sequence order. Checks numbering, links and every hash, then the recorded head."""
    previous: str | None = None
    for expected_seq, event in enumerate(events, start=1):
        if event.seq != expected_seq:
            return Verification(False, len(events), head_hash, event.seq, f"Entry {expected_seq} is missing")
        if event.prev_hash != previous:
            return Verification(False, len(events), head_hash, event.seq, "Link to the previous entry is broken")
        if hash_of(event) != event.hash:
            return Verification(False, len(events), head_hash, event.seq, "Entry was changed after it was recorded")
        previous = event.hash
    if previous != head_hash:
        return Verification(False, len(events), head_hash, len(events), "Latest entries are missing")
    return Verification(True, len(events), head_hash)
