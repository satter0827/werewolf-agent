import json
import logging
import sys
from pathlib import Path

import structlog

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.commons.logging import (
    bind_log_context,
    configure_logging,
    get_log_context,
)
from werewolf_agent.commons.security.redaction import redact_mapping, redact_text


def _settings(tmp_path: Path, **overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "_env_file": None,
        "log_dir": tmp_path,
        "log_file_name": "test.jsonl",
        "log_level": "DEBUG",
        "log_output": "file",
    }
    values.update(overrides)
    return AppSettings(**values)


def _flush_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def _read_log(path: Path) -> dict[str, object]:
    _flush_handlers()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1
    return json.loads(lines[0])


def test_configure_logging_writes_ecs_jsonl_with_context_and_extra(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    configure_logging(settings)

    logger = logging.getLogger("werewolf_agent.tests")
    with bind_log_context(trace_id="trace-1", method="GET", path="/api/v1/health"):
        logger.info(
            "hello %s",
            "world",
            extra={
                "api_key": "secret-value",
                "count": 2,
                "http_status": 200,
                "duration_ms": 1.25,
            },
        )

    payload = _read_log(settings.log_file_path)

    assert payload["@timestamp"]
    assert payload["log.level"] == "INFO"
    assert payload["log.logger"] == "werewolf_agent.tests"
    assert payload["message"] == "hello world"
    assert payload["service.name"] == "werewolf-agent-api"
    assert payload["service.version"] == "0.1.0"
    assert payload["event.dataset"] == "werewolf_agent.tests"
    assert payload["trace.id"] == "trace-1"
    assert payload["http.request.method"] == "GET"
    assert payload["url.path"] == "/api/v1/health"
    assert payload["http.response.status_code"] == 200
    assert payload["event.duration"] == 1_250_000
    assert payload["api_key"] == "[REDACTED]"
    assert payload["count"] == 2


def test_structlog_uses_same_jsonl_processors(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    configure_logging(settings)

    structlog.get_logger("werewolf_agent.tests.structlog").info(
        "structured event",
        game_id="game-1",
        token="secret-token",
    )

    payload = _read_log(settings.log_file_path)

    assert payload["log.level"] == "INFO"
    assert payload["log.logger"] == "werewolf_agent.tests.structlog"
    assert payload["message"] == "structured event"
    assert payload["game_id"] == "game-1"
    assert payload["token"] == "[REDACTED]"


def test_bound_log_context_does_not_leak_outside_scope() -> None:
    assert get_log_context() == {}

    with bind_log_context(game_id="game-1"):
        assert get_log_context()["game_id"] == "game-1"

    assert "game_id" not in get_log_context()


def test_configure_logging_includes_redacted_exception_payload(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    configure_logging(settings)
    logger = logging.getLogger("werewolf_agent.tests")

    try:
        raise RuntimeError("token=secret-value")
    except RuntimeError:
        logger.exception("failed authorization=Bearer abc")

    payload = _read_log(settings.log_file_path)

    assert payload["log.level"] == "ERROR"
    assert payload["message"] == "failed authorization=[REDACTED]"
    assert payload["error.type"] == "RuntimeError"
    assert payload["error.message"] == "token=[REDACTED]"
    assert "RuntimeError: token=[REDACTED]" in payload["error.stack_trace"]


def test_configure_logging_supports_stdout_output(
    tmp_path: Path,
    capsys,
) -> None:
    settings = _settings(tmp_path, log_output="stdout")
    configure_logging(settings)

    logging.getLogger("werewolf_agent.tests").warning("stdout log")
    _flush_handlers()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["message"] == "stdout log"
    assert not settings.log_file_path.exists()


def test_configure_logging_supports_both_and_none_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    both_settings = _settings(tmp_path / "both", log_output="both")
    configure_logging(both_settings)
    logging.getLogger("werewolf_agent.tests").error("both log")
    both_payload = _read_log(both_settings.log_file_path)
    captured = capsys.readouterr()
    assert json.loads(captured.err)["message"] == "both log"
    assert both_payload["message"] == "both log"

    none_settings = _settings(tmp_path / "none", log_output="none")
    configure_logging(none_settings)
    logging.getLogger("werewolf_agent.tests").critical("dropped log")
    _flush_handlers()
    assert not none_settings.log_file_path.exists()


def test_redact_mapping_masks_sensitive_keys_recursively() -> None:
    redacted = redact_mapping(
        {
            "safe": "value",
            "authorization": "Bearer abc",
            "nested": {"api_token": "abc", "model": "fake_llm"},
            "items": [{"password": "pw"}],
        }
    )

    assert redacted == {
        "safe": "value",
        "authorization": "[REDACTED]",
        "nested": {"api_token": "[REDACTED]", "model": "fake_llm"},
        "items": [{"password": "[REDACTED]"}],
    }


def test_redact_text_masks_common_sensitive_assignments() -> None:
    assert redact_text("api_key=abc token: def safe=value") == (
        "api_key=[REDACTED] token: [REDACTED] safe=value"
    )


def teardown_module() -> None:
    logging.shutdown()
    logging.basicConfig(handlers=[logging.NullHandler()], force=True)
    structlog.contextvars.clear_contextvars()
    sys.stderr.flush()
    sys.stdout.flush()
