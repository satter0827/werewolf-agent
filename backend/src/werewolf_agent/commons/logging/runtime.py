"""Logging helpers for interface processes."""

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Final, TextIO, cast

import structlog
from structlog.typing import EventDict

from werewolf_agent.commons.configuration.settings import AppSettings
from werewolf_agent.commons.security.redaction import redact_mapping, redact_text
from werewolf_agent.commons.shared.constants import JSON_ENCODING, JSON_SEPARATORS

LOG_OUTPUT_BOTH: Final = "both"
LOG_OUTPUT_FILE: Final = "file"
LOG_OUTPUT_NONE: Final = "none"
LOG_OUTPUT_STDOUT: Final = "stdout"
THIRD_PARTY_LOGGER_NAMES: Final = (
    "alembic",
    "httpcore",
    "httpx",
    "sqlalchemy",
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
)

Processor = Callable[[Any, str, EventDict], EventDict]


def configure_logging(settings: AppSettings) -> None:
    """Configure process-level structured logging."""
    formatter = _processor_formatter(settings)
    handlers = _handlers(settings, formatter)

    stdlib_logging.basicConfig(
        level=settings.log_level,
        handlers=handlers or [stdlib_logging.NullHandler()],
        force=True,
    )
    _configure_structlog()
    _configure_third_party_loggers(settings.log_third_party_level)
    stdlib_logging.captureWarnings(True)


def get_log_context() -> dict[str, str]:
    """Return the current structured logging context."""
    return {str(key): str(value) for key, value in structlog.contextvars.get_contextvars().items()}


@contextmanager
def bind_log_context(**values: object) -> Iterator[None]:
    """Temporarily bind structured logging context values."""
    normalized_values = {key: str(value) for key, value in values.items() if value is not None}
    tokens = structlog.contextvars.bind_contextvars(**normalized_values)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)


def _configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            _add_exception_fields,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="@timestamp"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _processor_formatter(settings: AppSettings) -> structlog.stdlib.ProcessorFormatter:
    foreign_pre_chain = cast(
        Any,
        [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.ExtraAdder(),
            structlog.processors.StackInfoRenderer(),
            _add_exception_fields,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="@timestamp"),
        ],
    )
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=foreign_pre_chain,
        processors=[
            _add_service_fields(settings),
            _normalize_ecs_fields,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _redact_event_dict,
            structlog.processors.JSONRenderer(serializer=_json_dumps),
        ],
    )


def _handlers(
    settings: AppSettings,
    formatter: stdlib_logging.Formatter,
) -> list[stdlib_logging.Handler]:
    output = settings.log_output
    if output == LOG_OUTPUT_NONE:
        return []

    handlers: list[stdlib_logging.Handler] = []
    if output in {LOG_OUTPUT_FILE, LOG_OUTPUT_BOTH}:
        handlers.append(_file_handler(settings, formatter))
    if output == LOG_OUTPUT_STDOUT:
        handlers.append(_stream_handler(sys.stdout, settings.log_level, formatter))
    if output in {"stderr", LOG_OUTPUT_BOTH}:
        handlers.append(_stream_handler(sys.stderr, settings.log_level, formatter))
    return handlers


def _file_handler(
    settings: AppSettings,
    formatter: stdlib_logging.Formatter,
) -> TimedRotatingFileHandler:
    log_path = settings.log_file_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=settings.log_retention_days,
        encoding=JSON_ENCODING,
        utc=True,
        delay=True,
    )
    handler.setFormatter(formatter)
    handler.setLevel(settings.log_level)
    return handler


def _stream_handler(
    stream: TextIO,
    level: str,
    formatter: stdlib_logging.Formatter,
) -> stdlib_logging.StreamHandler[TextIO]:
    handler = stdlib_logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def _configure_third_party_loggers(level: str) -> None:
    for logger_name in THIRD_PARTY_LOGGER_NAMES:
        stdlib_logging.getLogger(logger_name).setLevel(level)


def _add_service_fields(settings: AppSettings) -> Processor:
    def processor(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service.name", settings.api_service_name)
        event_dict.setdefault("service.version", settings.api_version)
        return event_dict

    return processor


def _normalize_ecs_fields(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    _move_field(event_dict, "event", "message")
    _move_field(event_dict, "level", "log.level", transform=lambda value: str(value).upper())
    _move_field(event_dict, "logger", "log.logger")
    _move_field(event_dict, "trace_id", "trace.id")
    _move_field(event_dict, "method", "http.request.method")
    _move_field(event_dict, "http_method", "http.request.method")
    _move_field(event_dict, "path", "url.path")
    _move_field(event_dict, "http_path", "url.path")
    _move_field(event_dict, "http_status", "http.response.status_code")
    _move_field(event_dict, "duration_ms", "event.duration", transform=_duration_ms_to_ns)
    _move_field(event_dict, "error_code", "error.code")
    _move_field(event_dict, "exception", "error.stack_trace")

    record = event_dict.get("_record")
    exc_info = getattr(record, "exc_info", None)
    if exc_info is not None:
        exc_type, exc_value, _traceback = exc_info
        if exc_type is not None:
            event_dict.setdefault("error.type", exc_type.__name__)
        if exc_value is not None:
            event_dict.setdefault("error.message", redact_text(str(exc_value)))

    logger_name = event_dict.get("log.logger")
    if logger_name is not None:
        event_dict.setdefault("event.dataset", str(logger_name))
    event_dict.setdefault("event.dataset", "werewolf_agent")
    return event_dict


def _add_exception_fields(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    exc_info = event_dict.get("exc_info")
    if exc_info is True:
        exc_info = sys.exc_info()
    if exc_info is None:
        record = event_dict.get("_record")
        exc_info = getattr(record, "exc_info", None)
    if not isinstance(exc_info, tuple) or len(exc_info) != 3:
        return event_dict

    exc_type, exc_value, _traceback = exc_info
    if exc_type is not None:
        event_dict.setdefault("error.type", exc_type.__name__)
    if exc_value is not None:
        event_dict.setdefault("error.message", redact_text(str(exc_value)))
    return event_dict


def _redact_event_dict(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    return redact_mapping(event_dict)


def _move_field(
    event_dict: EventDict,
    source: str,
    target: str,
    *,
    transform: Callable[[object], object] | None = None,
) -> None:
    if source not in event_dict:
        return

    value = event_dict.pop(source)
    if target in event_dict:
        return
    event_dict[target] = transform(value) if transform is not None else value


def _duration_ms_to_ns(value: object) -> object:
    if not isinstance(value, (float, int, str)):
        return value
    try:
        return round(float(value) * 1_000_000)
    except (TypeError, ValueError):
        return value


def _json_dumps(value: object, **_kwargs: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=JSON_SEPARATORS,
    )
