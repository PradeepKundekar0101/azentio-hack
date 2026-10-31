"""App factory, routers and lifespan."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api import alerts, auth, claims, dashboard, documents, health, imports, reference, runs, users
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.security import session_principal
from app.db.session import Database
from app.documents.extract import Extractor
from app.storage.spaces import Storage


class SettingsCORSMiddleware:
    """CORS with origins from the settings loaded at startup, so importing the app never reads configuration."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.cors: ASGIApp | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if self.cors is None:
            settings: Settings = scope["app"].state.settings
            self.cors = CORSMiddleware(
                self.app,
                allow_origins=settings.cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        await self.cors(scope, receive, send)


def _api_router() -> APIRouter:
    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    # Every other API route needs a signed-in user; routes that need a role add their own check.
    protected = APIRouter(dependencies=[Depends(session_principal)])
    protected.include_router(reference.router)
    protected.include_router(imports.router)
    protected.include_router(runs.router)
    protected.include_router(claims.router)
    protected.include_router(alerts.router)
    protected.include_router(dashboard.router)
    protected.include_router(documents.router)
    protected.include_router(users.router)
    api.include_router(protected)
    return api


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        configure_logging(json=resolved.app_env == "demo")
        app.state.settings = resolved
        app.state.db = Database(resolved)
        app.state.storage = Storage.from_settings(resolved)
        app.state.extractor = Extractor(resolved)
        try:
            yield
        finally:
            await app.state.db.dispose()

    app = FastAPI(title="Claims Leakage API", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.add_middleware(SettingsCORSMiddleware)
    app.include_router(health.router)
    app.include_router(_api_router())
    return app


app = create_app()
