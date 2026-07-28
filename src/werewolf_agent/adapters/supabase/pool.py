"""Process-owned PostgreSQL connection pools."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

from werewolf_agent.contracts import AppError, ErrorCode


class SupabaseDatabaseUnavailableError(AppError):
    """Indicate that the database pool cannot provide a connection."""

    def __init__(self) -> None:
        """Create a retryable error without driver or DSN details."""
        super().__init__(
            "データベース接続を取得できませんでした。",
            code=ErrorCode.API_UNAVAILABLE,
            retryable=True,
        )


def create_database_pool(
    dsn: str,
    *,
    min_size: int,
    max_size: int,
    timeout: float,
    name: str,
) -> ConnectionPool[Any]:
    """Return a closed process-owned pool with safe connection defaults."""
    return ConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        name=name,
        open=False,
        kwargs={"row_factory": dict_row},
    )


def open_database_pool(pool: ConnectionPool[Any], *, timeout: float) -> None:
    """Open and verify a pool without exposing driver or DSN details."""
    try:
        pool.open()
        pool.wait(timeout=timeout)
    except (psycopg.Error, PoolClosed, PoolTimeout, RuntimeError) as exc:
        pool.close()
        raise SupabaseDatabaseUnavailableError from exc


@contextmanager
def borrow_database_connection(pool: Any) -> Iterator[Any]:
    """Borrow one connection and normalize pool acquisition failures."""
    try:
        with pool.connection() as connection:
            yield connection
    except (psycopg.InterfaceError, psycopg.OperationalError, PoolClosed, PoolTimeout) as exc:
        raise SupabaseDatabaseUnavailableError from exc


__all__ = [
    "SupabaseDatabaseUnavailableError",
    "borrow_database_connection",
    "create_database_pool",
    "open_database_pool",
]
