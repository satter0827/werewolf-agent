from pathlib import Path

import pytest
from pydantic import ValidationError

from werewolf_agent.commons.configuration import (
    DEFAULT_GAME_DEFAULT_PLAYER_COUNT,
    DEFAULT_GAME_MAX_PLAYERS,
    DEFAULT_GAME_MIN_PLAYERS,
    DEFAULT_SQLITE_PATH,
    PACKAGED_DEFAULTS,
    AppSettings,
    repository_root,
    split_csv,
    split_mapping,
)
from werewolf_agent.interface.application.settings import (
    build_game_usecase_config,
    build_llm_provider_config,
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


def test_packaged_defaults_are_loaded_from_resources() -> None:
    assert PACKAGED_DEFAULTS["app_name"] == "werewolf-agent"
    assert PACKAGED_DEFAULTS["llm_provider"] == "fake"
    assert PACKAGED_DEFAULTS["llm_prompt_file"] == ""


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

    assert settings.log_level == PACKAGED_DEFAULTS["log_level"]
    assert settings.log_output == PACKAGED_DEFAULTS["log_output"]
    assert settings.log_dir == Path(str(PACKAGED_DEFAULTS["log_dir"]))
    assert settings.log_file_name == PACKAGED_DEFAULTS["log_file_name"]
    assert settings.log_retention_days == PACKAGED_DEFAULTS["log_retention_days"]
    assert settings.log_third_party_level == PACKAGED_DEFAULTS["log_third_party_level"]
    assert settings.log_directory_path == repository_root() / str(PACKAGED_DEFAULTS["log_dir"])
    assert settings.log_file_path == settings.log_directory_path / settings.log_file_name
    assert settings.log_directory_path == repository_root() / ".werewolf-agent/logs"
    assert settings.log_file_path == repository_root() / ".werewolf-agent/logs/werewolf-agent.jsonl"
    assert settings.log_third_party_level == "WARNING"
    assert settings.cli_api_url == "http://127.0.0.1:8000/api/v1"
    assert settings.cli_http_timeout_seconds == 10.0
    assert settings.cli_max_steps == 64
    assert settings.cli_poll_interval_seconds == 0.0
    assert settings.cli_event_limit == 100
    assert settings.cli_output_format == "table"
    assert settings.streamlit_api_url == ""
    assert settings.streamlit_resolved_api_url == settings.cli_api_url
    assert settings.streamlit_http_timeout_seconds == 10.0
    assert settings.streamlit_refresh_interval_seconds == 5.0
    assert settings.streamlit_event_limit == 100
    assert settings.streamlit_turn_limit == 100
    assert settings.streamlit_run_limit == 20
    assert settings.streamlit_max_auto_steps == 64
    assert settings.streamlit_language == "ja"
    assert settings.streamlit_save_file == Path(".werewolf-agent/streamlit/saves.json")
    assert settings.streamlit_save_file_path == (
        repository_root() / ".werewolf-agent/streamlit/saves.json"
    )
    assert settings.streamlit_page_title == "Werewolf Agent"
    assert settings.streamlit_default_seed == 1
    assert settings.streamlit_default_human_player_id == "player-1"
    assert settings.streamlit_message_max_chars == 200
    assert settings.streamlit_service_name == "werewolf-agent-streamlit"
    assert settings.api_title == "Werewolf Agent API"
    assert settings.api_service_name == "werewolf-agent-api"
    assert settings.api_version == "0.1.0"
    assert settings.api_debug is False
    assert settings.llm_provider == "fake"
    assert settings.model == "fake-list-llm"
    assert settings.llm_prompt_path is None
    assert settings.llm_fake_responses_path is None
    assert settings.cors_allowed_methods_list == ["GET", "POST"]
    assert settings.cors_allowed_headers_list == ["*"]
    assert settings.game_role_name_map["werewolf"] == "人狼"
    assert settings.game_phase_name_map["day_discussion"] == "昼チャット"
    assert settings.game_min_players == DEFAULT_GAME_MIN_PLAYERS
    assert settings.game_max_players == DEFAULT_GAME_MAX_PLAYERS
    assert settings.game_default_player_count == DEFAULT_GAME_DEFAULT_PLAYER_COUNT
    assert settings.game_default_tie_break_policy == "no_elimination"
    assert settings.game_default_day_speech_turns == 1
    assert settings.game_default_allow_self_vote is False


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

    llm_config = build_llm_provider_config(settings)
    assert llm_config.provider == "fake"
    assert llm_config.model == "fake-list-llm"
    assert llm_config.prompt_file is None
    assert llm_config.fake_responses_file is None


def test_game_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEREWOLF_GAME_MIN_PLAYERS", "4")
    monkeypatch.setenv("WEREWOLF_GAME_MAX_PLAYERS", "10")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_PLAYER_COUNT", "7")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_TYPE", "llm")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_NAME", "Configurable LLM Agent")
    monkeypatch.setenv("WEREWOLF_LLM_PROMPT_FILE", "prompts/custom.toml")
    monkeypatch.setenv("WEREWOLF_LLM_FAKE_RESPONSES_FILE", "llm/fake.toml")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_RULESET_ID", "custom")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_RULESET_NAME", "Custom Rules")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_TIE_BREAK_POLICY", "random_elimination")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_DAY_SPEECH_TURNS", "2")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_ALLOW_SELF_VOTE", "true")
    monkeypatch.setenv("WEREWOLF_GAME_RULESET_DESCRIPTION_TEMPLATE", "{min_players}-{max_players}")
    monkeypatch.setenv("WEREWOLF_GAME_ROLE_NAMES", "villager:Villager")
    monkeypatch.setenv("WEREWOLF_GAME_PHASE_NAMES", "night:Night")
    monkeypatch.setenv("WEREWOLF_CLI_API_URL", "http://api.test/api/v1")
    monkeypatch.setenv("WEREWOLF_CLI_OUTPUT_FORMAT", "json")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_API_URL", "http://ui-api.test/api/v1")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_HTTP_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_REFRESH_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_EVENT_LIMIT", "50")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_TURN_LIMIT", "40")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_RUN_LIMIT", "9")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_LANGUAGE", "en")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_SAVE_FILE", "tmp/streamlit/saves.json")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_MAX_AUTO_STEPS", "12")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_PAGE_TITLE", "Werewolf Console")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_DEFAULT_SEED", "33")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_DEFAULT_HUMAN_PLAYER_ID", "player-2")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_MESSAGE_MAX_CHARS", "120")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_SERVICE_NAME", "test-streamlit")
    monkeypatch.setenv("WEREWOLF_API_SERVICE_NAME", "test-api")

    settings = AppSettings(_env_file=None)

    assert settings.game_min_players == 4
    assert settings.game_max_players == 10
    assert settings.game_default_player_count == 7
    assert settings.game_supported_agent_type == "llm"
    assert settings.game_supported_agent_name == "Configurable LLM Agent"
    assert settings.llm_prompt_path == repository_root() / "prompts/custom.toml"
    assert settings.llm_fake_responses_path == repository_root() / "llm/fake.toml"
    assert settings.game_default_ruleset_id == "custom"
    assert settings.game_default_ruleset_name == "Custom Rules"
    assert settings.game_default_tie_break_policy == "random_elimination"
    assert settings.game_default_day_speech_turns == 2
    assert settings.game_default_allow_self_vote is True
    assert settings.game_ruleset_description_template == "{min_players}-{max_players}"
    assert settings.game_role_name_map == {"villager": "Villager"}
    assert settings.game_phase_name_map == {"night": "Night"}
    assert settings.cli_api_url == "http://api.test/api/v1"
    assert settings.cli_output_format == "json"
    assert settings.streamlit_api_url == "http://ui-api.test/api/v1"
    assert settings.streamlit_resolved_api_url == "http://ui-api.test/api/v1"
    assert settings.streamlit_http_timeout_seconds == 5.0
    assert settings.streamlit_refresh_interval_seconds == 2.0
    assert settings.streamlit_event_limit == 50
    assert settings.streamlit_turn_limit == 40
    assert settings.streamlit_run_limit == 9
    assert settings.streamlit_max_auto_steps == 12
    assert settings.streamlit_language == "en"
    assert settings.streamlit_save_file_path == repository_root() / "tmp/streamlit/saves.json"
    assert settings.streamlit_page_title == "Werewolf Console"
    assert settings.streamlit_default_seed == 33
    assert settings.streamlit_default_human_player_id == "player-2"
    assert settings.streamlit_message_max_chars == 120
    assert settings.streamlit_service_name == "test-streamlit"
    assert settings.api_service_name == "test-api"


def test_logging_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WEREWOLF_LOG_LEVEL", "debug")
    monkeypatch.setenv("WEREWOLF_LOG_OUTPUT", "both")
    monkeypatch.setenv("WEREWOLF_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("WEREWOLF_LOG_FILE_NAME", "env.jsonl")
    monkeypatch.setenv("WEREWOLF_LOG_RETENTION_DAYS", "7")
    monkeypatch.setenv("WEREWOLF_LOG_THIRD_PARTY_LEVEL", "error")

    settings = AppSettings(_env_file=None)

    assert settings.log_level == "DEBUG"
    assert settings.log_output == "both"
    assert settings.log_directory_path == tmp_path
    assert settings.log_file_path == tmp_path / "env.jsonl"
    assert settings.log_retention_days == 7
    assert settings.log_third_party_level == "ERROR"


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


def test_logging_settings_normalize_supported_values(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        log_level="debug",
        log_output="BOTH",
        log_dir=tmp_path,
        log_file_name="custom.jsonl",
        log_third_party_level="error",
    )

    assert settings.log_level == "DEBUG"
    assert settings.log_output == "both"
    assert settings.log_directory_path == tmp_path
    assert settings.log_file_path == tmp_path / "custom.jsonl"
    assert settings.log_third_party_level == "ERROR"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("log_level", "VERBOSE"),
        ("log_output", "socket"),
        ("log_third_party_level", "VERBOSE"),
        ("cli_output_format", "xml"),
        ("streamlit_language", "fr"),
        ("game_default_tie_break_policy", "coin_flip"),
        ("game_supported_agent_type", "bot"),
        ("llm_provider", "openai"),
    ],
)
def test_choice_settings_reject_invalid_values(field_name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **{field_name: value})


def test_log_file_name_rejects_paths() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, log_file_name="../app.jsonl")
