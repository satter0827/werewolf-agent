"""Context values attached to structured application logs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar(
    "werewolf_log_context",
    default=None,
)


def get_log_context() -> dict[str, str]:
    """Return the current structured logging context."""
    context = _LOG_CONTEXT.get()
    if context is None:
        return {}
    return dict(context)


@contextmanager
def bind_log_context(**values: object) -> Iterator[None]:
    """Temporarily bind structured logging context values."""
    next_context = get_log_context()
    for key, value in values.items():
        if value is not None:
            next_context[key] = str(value)

    token = _LOG_CONTEXT.set(next_context)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)
