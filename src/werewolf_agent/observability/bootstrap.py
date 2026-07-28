"""Observability startup helpers for application processes."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from werewolf_agent.observability.logging import configure_observability
from werewolf_agent.settings import AppSettings, load_app_settings


def configure_entrypoint_logging(
    settings: AppSettings | None = None,
    *,
    default_log_file_name: str | None = None,
    service_name: str | None = None,
) -> AppSettings:
    """Configure logging for an entry point process and return its settings."""
    try:
        loaded_settings = settings or load_app_settings()
    except Exception as error:
        emit_bootstrap_failure(service_name=service_name, error=error)
        raise
    if default_log_file_name is not None:
        loaded_settings = loaded_settings.with_log_file_name(default_log_file_name)
    configure_observability(loaded_settings, service_name=service_name)
    return loaded_settings


def emit_bootstrap_failure(*, service_name: str | None, error: BaseException) -> None:
    """設定成立前の失敗を値を含まないJSONとしてstderrへ出す."""
    payload = {
        "@timestamp": datetime.now(UTC).isoformat(),
        "log.level": "ERROR",
        "service.name": service_name or "werewolf-agent",
        "event.action": "application.bootstrap.failed",
        "event.outcome": "failure",
        "error.code": "config.invalid",
        "error.type": type(error).__name__,
        "error.message": "起動設定またはresourceを検証できませんでした。",
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
