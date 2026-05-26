"""Structured application log formatters."""

from __future__ import annotations

import json
import logging as stdlib_logging
from datetime import UTC, datetime
from typing import Final

from werewolf_agent.commons.logging.context import get_log_context
from werewolf_agent.commons.security.redaction import redact_mapping
from werewolf_agent.commons.shared.constants import (
    BASE_LOG_RECORD_ARGS,
    BASE_LOG_RECORD_EXC_INFO,
    BASE_LOG_RECORD_LEVEL,
    BASE_LOG_RECORD_LINENO,
    BASE_LOG_RECORD_MESSAGE,
    BASE_LOG_RECORD_NAME,
    BASE_LOG_RECORD_PATHNAME,
    JSON_SEPARATORS,
    LOG_FIELD_EXCEPTION,
    LOG_FIELD_EXCEPTION_MESSAGE,
    LOG_FIELD_EXCEPTION_STACKTRACE,
    LOG_FIELD_EXCEPTION_TYPE,
    LOG_FIELD_EXTRA,
    LOG_FIELD_LEVEL,
    LOG_FIELD_LOGGER,
    LOG_FIELD_MESSAGE,
    LOG_FIELD_TIMESTAMP,
    PRIVATE_ATTRIBUTE_PREFIX,
    STANDARD_LOG_MESSAGE_ATTRIBUTES,
    UTC_ISO_SUFFIX,
    UTC_OFFSET_SUFFIX,
)

_BASE_LOG_RECORD = stdlib_logging.LogRecord(
    BASE_LOG_RECORD_NAME,
    BASE_LOG_RECORD_LEVEL,
    BASE_LOG_RECORD_PATHNAME,
    BASE_LOG_RECORD_LINENO,
    BASE_LOG_RECORD_MESSAGE,
    BASE_LOG_RECORD_ARGS,
    BASE_LOG_RECORD_EXC_INFO,
)
STANDARD_LOG_RECORD_ATTRIBUTES: Final = frozenset(_BASE_LOG_RECORD.__dict__) | frozenset(
    STANDARD_LOG_MESSAGE_ATTRIBUTES
)


class JsonFormatter(stdlib_logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload: dict[str, object] = {
            LOG_FIELD_TIMESTAMP: datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace(UTC_OFFSET_SUFFIX, UTC_ISO_SUFFIX),
            LOG_FIELD_LEVEL: record.levelname,
            LOG_FIELD_LOGGER: record.name,
            LOG_FIELD_MESSAGE: record.getMessage(),
        }
        payload.update(get_log_context())

        extra = _record_extra(record)
        if extra:
            payload[LOG_FIELD_EXTRA] = redact_mapping(extra)

        exception = self._exception_payload(record)
        if exception is not None:
            payload[LOG_FIELD_EXCEPTION] = exception

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
            LOG_FIELD_EXCEPTION_TYPE: exc_type.__name__ if exc_type is not None else None,
            LOG_FIELD_EXCEPTION_MESSAGE: str(exc_value) if exc_value is not None else "",
            LOG_FIELD_EXCEPTION_STACKTRACE: self.formatException(record.exc_info),
        }


def _record_extra(record: stdlib_logging.LogRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in STANDARD_LOG_RECORD_ATTRIBUTES
        and not key.startswith(PRIVATE_ATTRIBUTE_PREFIX)
    }
