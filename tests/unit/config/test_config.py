from pathlib import Path

import pytest
from pydantic import ValidationError

from werewolf_agent.config import (
    DEFAULT_DJANGO_SQLITE_PATH,
    AppSettings,
    repository_root,
    split_csv,
)


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
    assert settings.django_database_url == ""
    assert settings.django_database_config == {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": repository_root() / "tmp/test.sqlite3",
    }


def test_database_url_uses_django_database_url_parser() -> None:
    pytest.importorskip("dj_database_url")
    settings = AppSettings(
        _env_file=None,
        database_url="postgres://werewolf_agent:secret@example.test:5432/werewolf_agent",
    )

    database_config = settings.django_database_config

    assert settings.django_database_url.endswith("@example.test:5432/werewolf_agent")
    assert database_config["ENGINE"] == "django.db.backends.postgresql"
    assert database_config["HOST"] == "example.test"
    assert database_config["PORT"] == 5432
    assert database_config["CONN_MAX_AGE"] == 600
    assert database_config["CONN_HEALTH_CHECKS"] is True


def test_logging_settings_have_safe_defaults() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.log_output == "stderr"
    assert settings.django_sqlite_path == DEFAULT_DJANGO_SQLITE_PATH
    assert settings.django_sqlite_database == repository_root() / DEFAULT_DJANGO_SQLITE_PATH


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


def test_django_secret_key_must_be_explicit_when_debug_is_disabled() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, django_debug=False)

    with pytest.raises(ValidationError):
        AppSettings(
            _env_file=None,
            django_debug=False,
            django_secret_key="short-secret",
        )

    settings = AppSettings(
        _env_file=None,
        django_debug=False,
        django_secret_key="test-only-production-secret-with-enough-length-123456",
    )

    assert (
        settings.django_secret_key.get_secret_value()
        == "test-only-production-secret-with-enough-length-123456"
    )
