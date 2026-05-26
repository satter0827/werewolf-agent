import json
import logging
import sys

from werewolf_agent.commons.log_context import bind_log_context
from werewolf_agent.commons.logging import (
    JsonFormatter,
    build_django_logging_config,
)
from werewolf_agent.commons.redaction import (
    redact_mapping,
)
from werewolf_agent.config import AppSettings


def _format_record(record: logging.LogRecord) -> dict[str, object]:
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_outputs_parseable_record_with_context_and_extra() -> None:
    record = logging.LogRecord(
        "werewolf_agent.tests",
        logging.INFO,
        __file__,
        10,
        "hello %s",
        ("world",),
        None,
    )
    record.api_key = "secret-value"
    record.count = 2

    with bind_log_context(run_id="run-1", trace_id="trace-1"):
        payload = _format_record(record)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "werewolf_agent.tests"
    assert payload["message"] == "hello world"
    assert payload["run_id"] == "run-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["extra"] == {"api_key": "[REDACTED]", "count": 2}


def test_bound_log_context_does_not_leak_outside_scope() -> None:
    record = logging.LogRecord(
        "werewolf_agent.tests",
        logging.INFO,
        __file__,
        10,
        "hello",
        (),
        None,
    )

    with bind_log_context(game_id="game-1"):
        scoped_payload = _format_record(record)
    unscoped_payload = _format_record(record)

    assert scoped_payload["game_id"] == "game-1"
    assert "game_id" not in unscoped_payload


def test_json_formatter_includes_exception_payload() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            "werewolf_agent.tests",
            logging.ERROR,
            __file__,
            10,
            "failed",
            (),
            sys.exc_info(),
        )

    payload = _format_record(record)

    assert payload["exception"]["type"] == "RuntimeError"
    assert payload["exception"]["message"] == "boom"
    assert "RuntimeError: boom" in payload["exception"]["stacktrace"]


def test_json_formatter_includes_error_metadata_extra() -> None:
    record = logging.LogRecord(
        "werewolf_agent.tests",
        logging.ERROR,
        __file__,
        10,
        "failed",
        (),
        None,
    )
    record.error_code = "game.invalid_action"
    record.retryable = False

    with bind_log_context(trace_id="trace-1"):
        payload = _format_record(record)

    assert payload["trace_id"] == "trace-1"
    assert payload["extra"] == {
        "error_code": "game.invalid_action",
        "retryable": False,
    }


def test_redact_mapping_masks_sensitive_keys_recursively() -> None:
    redacted = redact_mapping(
        {
            "safe": "value",
            "authorization": "Bearer abc",
            "nested": {"api_token": "abc", "model": "dummy"},
            "items": [{"password": "pw"}],
        }
    )

    assert redacted == {
        "safe": "value",
        "authorization": "[REDACTED]",
        "nested": {"api_token": "[REDACTED]", "model": "dummy"},
        "items": [{"password": "[REDACTED]"}],
    }


def test_build_django_logging_config_uses_shared_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        log_level="debug",
        log_format="console",
        log_output="stdout",
    )

    logging_config = build_django_logging_config(settings)

    assert logging_config["root"]["level"] == "DEBUG"
    assert logging_config["handlers"]["default"]["formatter"] == "console"
    assert logging_config["handlers"]["default"]["stream"] == "ext://sys.stdout"
