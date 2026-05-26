from pathlib import Path

import pytest
from pydantic import ValidationError

import werewolf_agent.config as legacy_config
from werewolf_agent.configuration import (
    DEFAULT_DJANGO_SQLITE_PATH,
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    AppSettings,
    build_game_usecase_settings,
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
    assert settings.game_min_players == DEFAULT_GAME_MIN_PLAYERS
    assert settings.game_max_players == DEFAULT_GAME_MAX_PLAYERS
    assert settings.game_default_player_count == DEFAULT_GAME_DEFAULT_PLAYER_COUNT


def test_game_usecase_settings_are_built_from_application_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        game_min_players=4,
        game_max_players=10,
        game_default_player_count=7,
        game_supported_agent_type="dummy",
        game_supported_agent_name="Dummy Agent",
        game_default_ruleset_id="default",
        game_default_ruleset_name="Custom Rules",
    )

    usecase_settings = build_game_usecase_settings(settings)

    assert usecase_settings.min_players == 4
    assert usecase_settings.max_players == 10
    assert usecase_settings.default_player_count == 7
    assert usecase_settings.supported_agent_type == "dummy"
    assert usecase_settings.supported_agent_name == "Dummy Agent"
    assert usecase_settings.default_ruleset_id == "default"
    assert usecase_settings.default_ruleset_name == "Custom Rules"
    assert usecase_settings.default_ruleset_description == (
        "4〜10人向けの最小同期 API ルールセットです。"
    )


def test_game_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEREWOLF_GAME_MIN_PLAYERS", "4")
    monkeypatch.setenv("WEREWOLF_GAME_MAX_PLAYERS", "10")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_PLAYER_COUNT", "7")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_TYPE", "dummy")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_NAME", "Configurable Dummy")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_RULESET_ID", "custom")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_RULESET_NAME", "Custom Rules")

    settings = AppSettings(_env_file=None)

    assert settings.game_min_players == 4
    assert settings.game_max_players == 10
    assert settings.game_default_player_count == 7
    assert settings.game_supported_agent_type == "dummy"
    assert settings.game_supported_agent_name == "Configurable Dummy"
    assert settings.game_default_ruleset_id == "custom"
    assert settings.game_default_ruleset_name == "Custom Rules"


def test_game_settings_reject_inconsistent_player_counts() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, game_min_players=9, game_max_players=8)

    with pytest.raises(ValidationError):
        AppSettings(
            _env_file=None,
            game_min_players=5,
            game_max_players=8,
            game_default_player_count=9,
        )


def test_legacy_config_module_reexports_configuration() -> None:
    assert legacy_config.AppSettings is AppSettings
    assert legacy_config.build_game_usecase_settings is build_game_usecase_settings


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
