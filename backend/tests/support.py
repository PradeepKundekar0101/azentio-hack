"""Test helpers shared by fixtures and tests."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text

from app.db.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


def migrate(database_url: str) -> None:
    """Drop everything in the public schema, then apply every migration."""
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("drop schema public cascade"))
        connection.execute(text("create schema public"))
    engine.dispose()
    command.upgrade(alembic_config(database_url), "head")


def truncate_all(connection: Connection) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    connection.execute(text(f"truncate {tables} restart identity cascade"))
