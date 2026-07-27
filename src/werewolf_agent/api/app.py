"""API process entrypoint."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from werewolf_agent.api.bootstrap import create_app
from werewolf_agent.observability import configure_entrypoint_logging
from werewolf_agent.settings import AppSettings

logger = logging.getLogger(__name__)


def build_app() -> tuple[FastAPI, AppSettings]:
    """Loggingを初期化してからAPI applicationを構成する."""
    settings = configure_entrypoint_logging(
        default_log_file_name="api.jsonl",
        service_name="werewolf-agent-api",
    )
    try:
        return create_app(settings), settings
    except Exception:
        logger.exception(
            "api.bootstrap.failed",
            extra={
                "event_action": "api.bootstrap.failed",
                "event_outcome": "failure",
                "error_code": "config.invalid",
            },
        )
        raise


app, _settings = build_app()


def run() -> None:
    """Run the configured API server."""
    uvicorn.run(
        app,
        host=_settings.api_host,
        port=_settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
