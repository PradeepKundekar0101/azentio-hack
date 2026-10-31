from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select

from app.core import audit
from app.core.enums import RunScope
from app.core.errors import AppError, not_found
from app.core.security import CurrentUser
from app.db.models import ImportBatch, ProcessingRun
from app.db.session import SessionDep
from app.pipeline import run_in_background, start_run

router = APIRouter(prefix="/runs", tags=["runs"])


class RunIn(BaseModel):
    scope: Literal["batch", "all"]
    batch_id: int | None = None

    @model_validator(mode="after")
    def _batch_needs_id(self) -> "RunIn":
        if self.scope == "batch" and self.batch_id is None:
            raise ValueError("batch_id is required when scope is batch")
        return self


class RunFailure(BaseModel):
    claim_id: str
    error: str


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    scope: str
    batch_id: int | None
    started_at: datetime
    finished_at: datetime | None
    claims_processed: int
    claims_failed: int
    failures: list[RunFailure] | None
    rules_version: str
    error: str | None


@router.post("", status_code=202)
async def create_run(
    body: RunIn, request: Request, session: SessionDep, background: BackgroundTasks, username: CurrentUser
) -> RunOut:
    if body.scope == "batch" and await session.get(ImportBatch, body.batch_id) is None:
        raise not_found("Import")
    running = await session.scalar(select(ProcessingRun.id).where(ProcessingRun.status == "running").limit(1))
    if running is not None:
        raise AppError(409, "run_in_progress", f"Run {running} is still in progress")
    run = await start_run(session, RunScope(body.scope), body.batch_id)
    audit.record(session, username, "run_started", "processing_run", run.id, scope=body.scope, batch_id=body.batch_id)
    await session.commit()
    app = request.app
    background.add_task(run_in_background, app.state.db, app.state.settings, run.id, app.state.reader)
    return RunOut.model_validate(run)


@router.get("/latest")
async def latest_run(session: SessionDep) -> RunOut | None:
    run = await session.scalar(select(ProcessingRun).order_by(ProcessingRun.id.desc()).limit(1))
    return RunOut.model_validate(run) if run else None


@router.get("/{run_id}")
async def get_run(run_id: int, session: SessionDep) -> RunOut:
    run = await session.get(ProcessingRun, run_id)
    if run is None:
        raise not_found("Run")
    return RunOut.model_validate(run)
