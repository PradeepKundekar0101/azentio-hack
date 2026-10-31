import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import db
from app.config import Settings, get_settings
from app.storage import Storage

logger = logging.getLogger(__name__)

HEALTH_CHECK_TIMEOUT_SECONDS = 10


async def _check(name: str, probe: Callable[[], Awaitable[None]]) -> str:
    try:
        await asyncio.wait_for(probe(), timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("Health check failed: %s", name)
        return "error"
    return "ok"


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        engine = db.create_engine(resolved)
        app.state.engine = engine
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.storage = Storage.from_settings(resolved)
        yield
        await engine.dispose()

    app = FastAPI(title="Backend", lifespan=lifespan)

    @app.get("/health")
    async def health(request: Request, response: Response) -> dict:
        state = request.app.state
        checks = {
            "database": await _check("database", lambda: db.ping(state.engine)),
            "storage": await _check(
                "storage", lambda: asyncio.to_thread(state.storage.ping)
            ),
        }
        healthy = all(result == "ok" for result in checks.values())
        if not healthy:
            response.status_code = 503
        return {"status": "ok" if healthy else "unavailable", "checks": checks}

    return app


app = create_app()
