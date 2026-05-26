"""Logging configuration for CLI and Django entry points."""

from __future__ import annotations

import logging as stdlib_logging
import sys
from typing import TYPE_CHECKING, Any, TextIO

from werewolf_agent.commons.logging.formatters import JsonFormatter
from werewolf_agent.commons.shared.constants import (
    CONSOLE_LOG_FORMAT,
    DJANGO_LOGGER_NAME,
    DJANGO_LOGGING_KEY_CLASS,
    DJANGO_LOGGING_KEY_DISABLE_EXISTING_LOGGERS,
    DJANGO_LOGGING_KEY_FACTORY,
    DJANGO_LOGGING_KEY_FORMAT,
    DJANGO_LOGGING_KEY_FORMATTER,
    DJANGO_LOGGING_KEY_FORMATTERS,
    DJANGO_LOGGING_KEY_HANDLERS,
    DJANGO_LOGGING_KEY_LEVEL,
    DJANGO_LOGGING_KEY_LOGGERS,
    DJANGO_LOGGING_KEY_PROPAGATE,
    DJANGO_LOGGING_KEY_ROOT,
    DJANGO_LOGGING_KEY_STREAM,
    DJANGO_LOGGING_KEY_VERSION,
    JSON_FORMATTER_DOTTED_PATH,
    LOG_FORMAT_CONSOLE,
    LOG_FORMAT_JSON,
    LOG_HANDLER_DEFAULT,
    LOG_OUTPUT_STDOUT,
    LOG_STREAM_PREFIX,
    LOGGING_STREAM_HANDLER_CLASS,
    ROOT_LOGGING_VERSION,
    WEREWOLF_LOGGER_NAME,
)

if TYPE_CHECKING:
    from werewolf_agent.configuration import AppSettings


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
    formatter_name = (
        LOG_FORMAT_JSON if settings.log_format == LOG_FORMAT_JSON else LOG_FORMAT_CONSOLE
    )
    stream_name = f"{LOG_STREAM_PREFIX}{settings.log_output}"

    return {
        DJANGO_LOGGING_KEY_VERSION: ROOT_LOGGING_VERSION,
        DJANGO_LOGGING_KEY_DISABLE_EXISTING_LOGGERS: False,
        DJANGO_LOGGING_KEY_FORMATTERS: {
            LOG_FORMAT_JSON: {
                DJANGO_LOGGING_KEY_FACTORY: JSON_FORMATTER_DOTTED_PATH,
            },
            LOG_FORMAT_CONSOLE: {
                DJANGO_LOGGING_KEY_FORMAT: CONSOLE_LOG_FORMAT,
            },
        },
        DJANGO_LOGGING_KEY_HANDLERS: {
            LOG_HANDLER_DEFAULT: {
                DJANGO_LOGGING_KEY_CLASS: LOGGING_STREAM_HANDLER_CLASS,
                DJANGO_LOGGING_KEY_FORMATTER: formatter_name,
                DJANGO_LOGGING_KEY_LEVEL: settings.log_level,
                DJANGO_LOGGING_KEY_STREAM: stream_name,
            },
        },
        DJANGO_LOGGING_KEY_ROOT: {
            DJANGO_LOGGING_KEY_HANDLERS: [LOG_HANDLER_DEFAULT],
            DJANGO_LOGGING_KEY_LEVEL: settings.log_level,
        },
        DJANGO_LOGGING_KEY_LOGGERS: {
            DJANGO_LOGGER_NAME: {
                DJANGO_LOGGING_KEY_HANDLERS: [LOG_HANDLER_DEFAULT],
                DJANGO_LOGGING_KEY_LEVEL: settings.log_level,
                DJANGO_LOGGING_KEY_PROPAGATE: False,
            },
            WEREWOLF_LOGGER_NAME: {
                DJANGO_LOGGING_KEY_HANDLERS: [LOG_HANDLER_DEFAULT],
                DJANGO_LOGGING_KEY_LEVEL: settings.log_level,
                DJANGO_LOGGING_KEY_PROPAGATE: False,
            },
        },
    }


def _formatter_for(format_name: str) -> stdlib_logging.Formatter:
    if format_name == LOG_FORMAT_JSON:
        return JsonFormatter()
    return stdlib_logging.Formatter(CONSOLE_LOG_FORMAT)


def _stream_for(output_name: str) -> TextIO:
    if output_name == LOG_OUTPUT_STDOUT:
        return sys.stdout
    return sys.stderr
