"""Audit trail writes. Added to the caller's session, so the entry commits with the change it records."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def record(session: AsyncSession, actor: str, action: str, entity: str, entity_id: object, **details: Any) -> None:
    session.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=str(entity_id), details=details or None))
