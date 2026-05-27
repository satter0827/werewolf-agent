from pydantic import ValidationError

from werewolf_agent.interface.shared.runtime import settings_error_detail
from werewolf_agent.interface.shared.settings import AppSettings


def test_settings_error_detail_reports_first_invalid_setting() -> None:
    try:
        AppSettings(_env_file=None, log_level="verbose")
    except ValidationError as exc:
        detail = settings_error_detail(exc)

    assert detail.startswith("Invalid configuration for log_level:")
    assert "log_level must be one of" in detail
