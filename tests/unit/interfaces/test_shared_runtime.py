from pydantic import ValidationError

from werewolf_agent.config import AppSettings
from werewolf_agent.interfaces.shared.runtime import (
    build_interface_django_logging_config,
    settings_error_detail,
)


def test_settings_error_detail_reports_first_invalid_setting() -> None:
    try:
        AppSettings(_env_file=None, log_level="verbose")
    except ValidationError as exc:
        detail = settings_error_detail(exc)

    assert detail.startswith("Invalid configuration for log_level:")
    assert "log_level must be one of" in detail


def test_build_interface_django_logging_config_uses_shared_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        log_level="debug",
        log_format="console",
        log_output="stdout",
    )

    logging_config = build_interface_django_logging_config(settings)

    assert logging_config["root"]["level"] == "DEBUG"
    assert logging_config["handlers"]["default"]["formatter"] == "console"
    assert logging_config["handlers"]["default"]["stream"] == "ext://sys.stdout"
