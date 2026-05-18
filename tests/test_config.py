from pathlib import Path

import pytest
from pydantic import ValidationError

from werewolf_agent.config import AppSettings, repository_root, split_csv


def test_split_csv_removes_empty_items_and_whitespace() -> None:
    assert split_csv("localhost, 127.0.0.1,, testserver ") == [
        "localhost",
        "127.0.0.1",
        "testserver",
    ]


def test_django_settings_derive_lists_and_paths() -> None:
    settings = AppSettings(
        _env_file=None,
        django_allowed_hosts="localhost,127.0.0.1",
        django_csrf_trusted_origins="http://localhost:8000,https://example.test",
        django_sqlite_path=Path("tmp/test.sqlite3"),
    )

    assert settings.django_allowed_hosts_list == ["localhost", "127.0.0.1"]
    assert settings.django_csrf_trusted_origins_list == [
        "http://localhost:8000",
        "https://example.test",
    ]
    assert settings.django_sqlite_database == repository_root() / "tmp/test.sqlite3"


def test_logging_settings_have_safe_defaults() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.log_output == "stderr"


def test_logging_settings_normalize_supported_values() -> None:
    settings = AppSettings(
        _env_file=None,
        log_level="debug",
        log_format="CONSOLE",
        log_output="STDOUT",
    )

    assert settings.log_level == "DEBUG"
    assert settings.log_format == "console"
    assert settings.log_output == "stdout"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("log_level", "VERBOSE"),
        ("log_format", "plain"),
        ("log_output", "file"),
    ],
)
def test_logging_settings_reject_invalid_values(field_name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **{field_name: value})
