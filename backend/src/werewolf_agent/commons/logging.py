"""Structured application logging for CLI and Django entry points."""

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, TextIO

from werewolf_agent.commons.log_context import get_log_context
from werewolf_agent.commons.redaction import redact_mapping

if TYPE_CHECKING:
    from werewolf_agent.config import AppSettings

_BASE_LOG_RECORD = stdlib_logging.LogRecord("", 0, "", 0, "", (), None)
STANDARD_LOG_RECORD_ATTRIBUTES: Final = frozenset(_BASE_LOG_RECORD.__dict__) | frozenset(
    {"message", "asctime"}
)


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
            separators=(",", ":"),
        )

    def _exception_payload(self, record: stdlib_logging.LogRecord) -> dict[str, object] | None:
        if record.exc_info is None:
            return None

        exc_type, exc_value, _traceback = record.exc_info
        return {
            "type": exc_type.__name__ if exc_type is not None else None,
            "message": str(exc_value) if exc_value is not None else "",
            "stacktrace": self.formatException(record.exc_info),
        }


def configure_logging(settings: AppSettings) -> None:
    """Configure process-level logging for CLI entry points."""
    handler = stdlib_logging.StreamHandler(_stream_for(settings.log_output))
    handler.setFormatter(_formatter_for(settings.log_format))
    handler.setLevel(settings.log_level)

    stdlib_logging.basicConfig(
        level=settings.log_level,
        handlers=[handler],
        force=True,
    )
    stdlib_logging.captureWarnings(True)


def build_django_logging_config(settings: AppSettings) -> dict[str, Any]:
    """Build a Django LOGGING setting from shared application settings."""
    formatter_name = "json" if settings.log_format == "json" else "console"
    stream_name = f"ext://sys.{settings.log_output}"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "werewolf_agent.commons.logging.JsonFormatter",
            },
            "console": {
                "format": "%(levelname)s %(name)s: %(message)s",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
                "level": settings.log_level,
                "stream": stream_name,
            },
        },
        "root": {
            "handlers": ["default"],
            "level": settings.log_level,
        },
        "loggers": {
            "django": {
                "handlers": ["default"],
                "level": settings.log_level,
                "propagate": False,
            },
            "werewolf_agent": {
                "handlers": ["default"],
                "level": settings.log_level,
                "propagate": False,
            },
        },
    }


def _record_extra(record: stdlib_logging.LogRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in STANDARD_LOG_RECORD_ATTRIBUTES and not key.startswith("_")
    }


def _formatter_for(format_name: str) -> stdlib_logging.Formatter:
    if format_name == "json":
        return JsonFormatter()
    return stdlib_logging.Formatter("%(levelname)s %(name)s: %(message)s")


def _stream_for(output_name: str) -> TextIO:
    if output_name == "stdout":
        return sys.stdout
    return sys.stderr
