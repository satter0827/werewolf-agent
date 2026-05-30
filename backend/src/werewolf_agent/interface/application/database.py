"""SQLAlchemy engine and session setup for interface persistence."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TypeAlias

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from werewolf_agent.interface.runtime import AppSettings

SessionFactory: TypeAlias = sessionmaker[Session]


def create_database_engine(settings: AppSettings) -> Engine:
    """Create a SQLAlchemy engine from settings.

    Args:
        settings: Loaded application settings with database URL and SQLite path.

    Returns:
        Configured SQLAlchemy engine.

    """
    if not settings.configured_database_url:
        settings.sqlite_database_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args: dict[str, object] = {}
    engine_options: dict[str, object] = {}
    if settings.sqlalchemy_database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if settings.sqlalchemy_database_url in {"sqlite:///:memory:", "sqlite+pysqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool

    return create_engine(
        settings.sqlalchemy_database_url,
        connect_args=connect_args,
        future=True,
        hide_parameters=True,
        **engine_options,
    )


def create_session_factory(engine: Engine) -> SessionFactory:
    """Return a session factory bound to an engine.

    Args:
        engine: SQLAlchemy engine used by application repositories.

    Returns:
        Session factory configured for explicit unit-of-work boundaries.

    """
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    """Run one unit of work inside a database transaction.

    Args:
        session_factory: Factory used to create a SQLAlchemy session.

    Yields:
        An open session inside a transaction.

    """
    session = session_factory()
    try:
        with session.begin():
            yield session
    finally:
        session.close()
