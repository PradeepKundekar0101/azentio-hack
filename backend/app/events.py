"""analysis_events writer: every system and AI analysis step, appended for the audit trail."""

from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ActorType, EventType
from app.db.models import AnalysisEvent

CHUNK = 5000


def event(
    event_type: EventType,
    entity_type: str,
    entity_id: object,
    claim_id: str | None = None,
    actor_type: ActorType = ActorType.SYSTEM,
    model: str | None = None,
    prompt_version: str | None = None,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "event_type": event_type.value,
        "claim_id": claim_id,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "actor_type": actor_type.value,
        "model": model,
        "prompt_version": prompt_version,
        "payload": payload or None,
    }


async def write_events(session: AsyncSession, events: list[dict[str, Any]]) -> None:
    for start in range(0, len(events), CHUNK):
        await session.execute(insert(AnalysisEvent.__table__), events[start : start + CHUNK])
