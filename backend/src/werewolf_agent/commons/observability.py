"""Structured observability helpers for entry point processes."""

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from importlib import metadata
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Final, TextIO, cast

import structlog
from structlog.typing import EventDict

from werewolf_agent.commons.configuration.settings import APP_NAME, AppSettings
from werewolf_agent.commons.security.redaction import redact_mapping, redact_text
from werewolf_agent.commons.shared.constants import (
    JSON_ENCODING,
    JSON_SEPARATORS,
    LOG_OUTPUT_BOTH,
    LOG_OUTPUT_FILE,
    LOG_OUTPUT_NONE,
    LOG_OUTPUT_STDERR,
    LOG_OUTPUT_STDOUT,
)

THIRD_PARTY_LOGGER_NAMES: Final = (
    "httpcore",
    "httpx",
    "psycopg",
    "streamlit",
)
PRIVATE_GAMEPLAY_LOG_FIELDS: Final = (
    "actor_id",
    "game.action.type",
    "game_action_type",
    "known_roles",
    "night_action",
    "pending_actions",
    "player.id",
    "player_id",
    "private_state",
    "role",
    "target.id",
    "target_id",
)

Processor = Callable[[Any, str, EventDict], EventDict]


def configure_observability(settings: AppSettings, *, service_name: str | None = None) -> None:
    """Configure process-level structured observability."""
    formatter = _processor_formatter(settings, service_name=service_name)
    handlers = _handlers(settings, formatter)

    stdlib_logging.basicConfig(
        level=settings.log_level,
        handlers=handlers or [stdlib_logging.NullHandler()],
        force=True,
    )
    _configure_structlog()
    _configure_third_party_loggers(settings.log_third_party_level)
    stdlib_logging.captureWarnings(True)


def get_observation_context() -> dict[str, str]:
    """Return the current structured observation context."""
    return {str(key): str(value) for key, value in structlog.contextvars.get_contextvars().items()}


@contextmanager
def bind_observation_context(**values: object) -> Iterator[None]:
    """Temporarily bind structured observation context values."""
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


def _processor_formatter(
    settings: AppSettings,
    *,
    service_name: str | None,
) -> structlog.stdlib.ProcessorFormatter:
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
            _add_service_fields(settings, service_name=service_name),
            _drop_private_gameplay_fields,
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
    if output in {LOG_OUTPUT_STDERR, LOG_OUTPUT_BOTH}:
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


def _add_service_fields(settings: AppSettings, *, service_name: str | None) -> Processor:
    def processor(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
        _ = settings
        event_dict.setdefault("service.name", service_name or APP_NAME)
        event_dict.setdefault("service.version", _package_version())
        return event_dict

    return processor


def _package_version() -> str:
    try:
        return metadata.version(APP_NAME)
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _drop_private_gameplay_fields(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    return cast(EventDict, _without_private_gameplay_fields(event_dict))


def _without_private_gameplay_fields(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _without_private_gameplay_fields(item)
            for key, item in value.items()
            if str(key) not in PRIVATE_GAMEPLAY_LOG_FIELDS
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_without_private_gameplay_fields(item) for item in value]
    return value


def _normalize_ecs_fields(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    _move_field(event_dict, "event", "message")
    _move_field(event_dict, "level", "log.level", transform=lambda value: str(value).upper())
    _move_field(event_dict, "logger", "log.logger")
    _move_field(event_dict, "event_action", "event.action")
    _move_field(event_dict, "event_outcome", "event.outcome")
    _move_field(event_dict, "trace_id", "trace.id")
    _move_field(event_dict, "method", "http.request.method")
    _move_field(event_dict, "http_method", "http.request.method")
    _move_field(event_dict, "path", "url.path")
    _move_field(event_dict, "http_path", "url.path")
    _move_field(event_dict, "http_status", "http.response.status_code")
    _move_field(event_dict, "duration_ms", "event.duration", transform=_duration_ms_to_ns)
    _move_field(event_dict, "game_id", "game.id")
    _move_field(event_dict, "game_phase", "game.phase")
    _move_field(event_dict, "phase", "game.phase")
    _move_field(event_dict, "game_day", "game.day")
    _move_field(event_dict, "day", "game.day")
    _move_field(event_dict, "game_version", "game.version")
    _move_field(event_dict, "version", "game.version")
    _move_field(event_dict, "game_status", "game.status")
    _move_field(event_dict, "status", "game.status")
    _move_field(event_dict, "agent_type", "agent.type")
    _move_field(event_dict, "llm_provider", "llm.provider")
    _move_field(event_dict, "llm_model", "llm.model")
    _move_field(event_dict, "llm_base_url", "llm.base_url")
    _move_field(event_dict, "ui_action", "ui.action")
    _move_field(event_dict, "ui_stop_reason", "ui.stop_reason")
    _move_field(event_dict, "error_code", "error.code")
    _move_field(
        event_dict,
        "error_message",
        "error.message",
        transform=lambda value: redact_text(str(value)),
    )
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
