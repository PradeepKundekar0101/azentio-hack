"""Async SQLAlchemy engine and sessions on psycopg 3."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings

CONNECT_TIMEOUT_SECONDS = 5


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict[str, object] = {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    if settings.db_pool_mode == "transaction":
        # DO's PgBouncer pool in transaction mode cannot use server-side prepared statements.
        connect_args["prepare_threshold"] = None
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args=connect_args,
    )


class Database:
    """One engine and session factory per process (the API, a script, or a test)."""

    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(settings)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("select 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    database: Database = request.app.state.db
    async with database.sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
