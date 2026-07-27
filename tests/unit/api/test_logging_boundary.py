"""API entrypointの観測境界。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from werewolf_agent.api.errors import install_error_handlers
from werewolf_agent.contracts import ConfigError, ErrorCode

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"


def test_api_entrypoint_uses_the_shared_redacting_log_pipeline() -> None:
    source = (PACKAGE / "api" / "app.py").read_text(encoding="utf-8")
    assert "configure_entrypoint_logging(" in source
    assert 'default_log_file_name="api.jsonl"' in source


def test_handled_api_error_keeps_catalog_level_and_failure_fields(caplog) -> None:
    app = FastAPI()
    app.state.api_logger = logging.getLogger("test.api.handled")
    install_error_handlers(app)

    @app.get("/handled")
    def handled() -> None:
        raise ConfigError()

    with caplog.at_level(logging.INFO, logger="test.api.handled"):
        response = TestClient(app).get("/handled")

    assert response.status_code == 400
    record = caplog.records[-1]
    assert record.levelno == logging.INFO
    assert record.event_outcome == "failure"
    assert record.error_code == ErrorCode.CONFIG_INVALID_VALUE.value


def test_unhandled_api_error_has_stable_failure_fields(caplog) -> None:
    app = FastAPI()
    app.state.api_logger = logging.getLogger("test.api.unhandled")
    install_error_handlers(app)

    @app.get("/unhandled")
    def unhandled() -> None:
        raise RuntimeError("secret internal value")

    with caplog.at_level(logging.ERROR, logger="test.api.unhandled"):
        response = TestClient(app, raise_server_exceptions=False).get("/unhandled")

    assert response.status_code == 500
    record = caplog.records[-1]
    assert record.event_outcome == "failure"
    assert record.error_code == ErrorCode.INTERNAL_UNEXPECTED.value
