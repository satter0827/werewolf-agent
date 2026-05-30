from pydantic import ValidationError

from werewolf_agent.interface.runtime import AppSettings, settings_error_detail


def test_settings_error_detail_reports_first_invalid_setting() -> None:
    try:
        AppSettings(_env_file=None, log_level="verbose")
    except ValidationError as exc:
        detail = settings_error_detail(exc)

    assert detail.startswith("Invalid configuration for log_level:")
    assert "log_level must be one of" in detail
