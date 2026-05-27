from pathlib import Path

import pytest
from pydantic import ValidationError

from werewolf_agent.interface.application.settings import (
    build_fake_llm_config,
    build_game_usecase_config,
)
from werewolf_agent.interface.shared.settings import (
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_SQLITE_PATH,
    AppSettings,
    repository_root,
    split_csv,
    split_mapping,
)


def test_split_csv_removes_empty_items_and_whitespace() -> None:
    assert split_csv("localhost, 127.0.0.1,, https://ui.test ") == [
        "localhost",
        "127.0.0.1",
        "https://ui.test",
    ]


def test_split_mapping_parses_key_value_items() -> None:
    assert split_mapping("villager:村人, werewolf:人狼", field_name="names") == {
        "villager": "村人",
        "werewolf": "人狼",
    }


def test_database_settings_default_to_sqlite_path_under_generated_dir() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.sqlite_path == DEFAULT_SQLITE_PATH
    assert settings.sqlite_database_path == repository_root() / DEFAULT_SQLITE_PATH
    assert settings.configured_database_url == ""
    assert settings.sqlalchemy_database_url == (
        f"sqlite:///{(repository_root() / DEFAULT_SQLITE_PATH).as_posix()}"
    )


def test_sqlite_path_can_be_overridden() -> None:
    settings = AppSettings(_env_file=None, sqlite_path=Path("tmp/test.sqlite3"))

    assert settings.sqlite_database_path == repository_root() / "tmp/test.sqlite3"
    assert settings.sqlalchemy_database_url == (
        f"sqlite:///{(repository_root() / 'tmp/test.sqlite3').as_posix()}"
    )


def test_database_url_overrides_sqlite_and_normalizes_postgres_scheme() -> None:
    settings = AppSettings(
        _env_file=None,
        database_url="postgres://werewolf_agent:secret@example.test:5432/werewolf_agent",
    )

    assert settings.configured_database_url.endswith("@example.test:5432/werewolf_agent")
    assert settings.sqlalchemy_database_url.startswith("postgresql+psycopg://")


def test_logging_settings_have_safe_defaults() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.log_output == "stderr"
    assert settings.api_title == "Werewolf Agent API"
    assert settings.api_version == "0.1.0"
    assert settings.api_debug is False
    assert settings.llm_provider == "fake_llm"
    assert settings.model == "fake-llm-local"
    assert settings.fake_llm_strategy == "seeded"
    assert settings.fake_llm_speech_template_list
    assert settings.cors_allowed_methods_list == ["GET", "POST"]
    assert settings.cors_allowed_headers_list == ["*"]
    assert settings.game_role_name_map["werewolf"] == "人狼"
    assert settings.game_phase_name_map["day_discussion"] == "昼チャット"
    assert settings.game_min_players == DEFAULT_GAME_MIN_PLAYERS
    assert settings.game_max_players == DEFAULT_GAME_MAX_PLAYERS
    assert settings.game_default_player_count == DEFAULT_GAME_DEFAULT_PLAYER_COUNT


def test_game_usecase_config_is_built_from_interface_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        game_min_players=4,
        game_max_players=10,
        game_default_player_count=7,
        game_supported_agent_type="llm",
        game_supported_agent_name="LLM Agent",
        game_default_ruleset_id="default",
        game_default_ruleset_name="Custom Rules",
    )

    usecase_config = build_game_usecase_config(settings)

    assert usecase_config.min_players == 4
    assert usecase_config.max_players == 10
    assert usecase_config.default_player_count == 7
    assert usecase_config.supported_agent_type == "llm"
    assert usecase_config.default_ruleset_id == "default"

    fake_llm_config = build_fake_llm_config(settings)
    assert fake_llm_config.strategy == "seeded"
    assert fake_llm_config.randomness == settings.fake_llm_randomness
    assert fake_llm_config.speech_templates


def test_game_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEREWOLF_GAME_MIN_PLAYERS", "4")
    monkeypatch.setenv("WEREWOLF_GAME_MAX_PLAYERS", "10")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_PLAYER_COUNT", "7")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_TYPE", "llm")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_NAME", "Configurable LLM Agent")
    monkeypatch.setenv("WEREWOLF_FAKE_LLM_STRATEGY", "random")
    monkeypatch.setenv("WEREWOLF_FAKE_LLM_SPEECH_TEMPLATES", "hello {target_name}|watching")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_RULESET_ID", "custom")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_RULESET_NAME", "Custom Rules")
    monkeypatch.setenv("WEREWOLF_GAME_RULESET_DESCRIPTION_TEMPLATE", "{min_players}-{max_players}")
    monkeypatch.setenv("WEREWOLF_GAME_ROLE_NAMES", "villager:Villager")
    monkeypatch.setenv("WEREWOLF_GAME_PHASE_NAMES", "night:Night")

    settings = AppSettings(_env_file=None)

    assert settings.game_min_players == 4
    assert settings.game_max_players == 10
    assert settings.game_default_player_count == 7
    assert settings.game_supported_agent_type == "llm"
    assert settings.game_supported_agent_name == "Configurable LLM Agent"
    assert settings.fake_llm_strategy == "random"
    assert settings.fake_llm_speech_template_list == ["hello {target_name}", "watching"]
    assert settings.game_default_ruleset_id == "custom"
    assert settings.game_default_ruleset_name == "Custom Rules"
    assert settings.game_ruleset_description_template == "{min_players}-{max_players}"
    assert settings.game_role_name_map == {"villager": "Villager"}
    assert settings.game_phase_name_map == {"night": "Night"}


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

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, game_role_names="villager")

    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, game_ruleset_description_template="{unknown}")


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
        ("game_supported_agent_type", "fake_llm"),
        ("llm_provider", "openai"),
        ("fake_llm_strategy", "scripted"),
    ],
)
def test_choice_settings_reject_invalid_values(field_name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **{field_name: value})
