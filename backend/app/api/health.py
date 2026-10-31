import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(tags=["health"])

HEALTH_CHECK_TIMEOUT_SECONDS = 10

CheckResult = Literal["ok", "error"]


class HealthChecks(BaseModel):
    database: CheckResult
    storage: CheckResult


class HealthOut(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: HealthChecks


async def _check(name: str, probe: Callable[[], Awaitable[None]]) -> CheckResult:
    try:
        await asyncio.wait_for(probe(), timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
    except Exception as exc:
        log.warning("health_check_failed", check=name, error=type(exc).__name__)
        return "error"
    return "ok"


@router.get("/health")
async def health(request: Request, response: Response) -> HealthOut:
    state = request.app.state
    checks = HealthChecks(
        database=await _check("database", state.db.ping),
        storage=await _check("storage", lambda: asyncio.to_thread(state.storage.ping)),
    )
    healthy = checks.database == "ok" and checks.storage == "ok"
    if not healthy:
        response.status_code = 503
    return HealthOut(status="ok" if healthy else "unavailable", checks=checks)
