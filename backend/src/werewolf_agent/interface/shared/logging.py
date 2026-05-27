"""Logging helpers for interface processes."""

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Final, TextIO

from werewolf_agent.commons.security.redaction import redact_mapping, redact_text
from werewolf_agent.commons.shared.constants import JSON_SEPARATORS, LOG_CONTEXT_VAR_NAME
from werewolf_agent.interface.shared.settings import AppSettings

CONSOLE_LOG_FORMAT: Final = "%(levelname)s %(name)s: %(message)s"
LOG_FORMAT_JSON: Final = "json"
LOG_OUTPUT_STDOUT: Final = "stdout"
PRIVATE_ATTRIBUTE_PREFIX: Final = "_"
STANDARD_LOG_MESSAGE_ATTRIBUTES: Final = frozenset({"message", "asctime"})

_BASE_LOG_RECORD = stdlib_logging.LogRecord("", 0, "", 0, "", (), None)
STANDARD_LOG_RECORD_ATTRIBUTES: Final = frozenset(_BASE_LOG_RECORD.__dict__) | frozenset(
    STANDARD_LOG_MESSAGE_ATTRIBUTES
)
_LOG_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar(
    LOG_CONTEXT_VAR_NAME,
    default=None,
)


def configure_logging(settings: AppSettings) -> None:
    """Configure process-level logging."""
    handler = stdlib_logging.StreamHandler(_stream_for(settings.log_output))
    handler.setFormatter(_formatter_for(settings.log_format))
    handler.setLevel(settings.log_level)

    stdlib_logging.basicConfig(
        level=settings.log_level,
        handlers=[handler],
        force=True,
    )
    stdlib_logging.captureWarnings(True)


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


class JsonFormatter(stdlib_logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(get_log_context())

        extra = _record_extra(record)
        if extra:
            payload["extra"] = redact_mapping(extra)

        exception = self._exception_payload(record)
        if exception is not None:
            payload["exception"] = exception

        return json.dumps(
            redact_mapping(payload),
            ensure_ascii=False,
            default=str,
            separators=JSON_SEPARATORS,
        )

    def _exception_payload(self, record: stdlib_logging.LogRecord) -> dict[str, object] | None:
        if record.exc_info is None:
            return None

        exc_type, exc_value, _traceback = record.exc_info
        return {
            "type": exc_type.__name__ if exc_type is not None else None,
            "message": redact_text(str(exc_value)) if exc_value is not None else "",
            "stacktrace": redact_text(self.formatException(record.exc_info)),
        }


def _formatter_for(format_name: str) -> stdlib_logging.Formatter:
    if format_name == LOG_FORMAT_JSON:
        return JsonFormatter()
    return stdlib_logging.Formatter(CONSOLE_LOG_FORMAT)


def _stream_for(output_name: str) -> TextIO:
    if output_name == LOG_OUTPUT_STDOUT:
        return sys.stdout
    return sys.stderr


def _record_extra(record: stdlib_logging.LogRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in STANDARD_LOG_RECORD_ATTRIBUTES
        and not key.startswith(PRIVATE_ATTRIBUTE_PREFIX)
    }
