import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from werewolf_agent.interface.application.settings import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
    build_llm_provider_config,
)
from werewolf_agent.interface.runtime import (
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


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep default-setting assertions independent from caller environment."""
    for key in list(os.environ):
        if key.startswith("WEREWOLF_") or key in {"DATABASE_URL", "OPENAI_API_KEY"}:
            monkeypatch.delenv(key, raising=False)


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
    assert PACKAGED_DEFAULTS["llm_provider"] == "lmstudio"
    assert PACKAGED_DEFAULTS["model"] == "auto"
    assert PACKAGED_DEFAULTS["llm_base_url"] == "http://127.0.0.1:1234/v1"
    assert PACKAGED_DEFAULTS["llm_prompt_file"] == ""
    assert PACKAGED_DEFAULTS["llm_players_file"] == ""
    assert PACKAGED_DEFAULTS["game_rules_file"] == ""
    assert PACKAGED_DEFAULTS["game_roles_file"] == ""


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
    assert settings.cli_http_timeout_seconds == 5.0
    assert settings.advance_job_poll_interval_seconds == 0.25
    assert settings.advance_job_poll_timeout_seconds == 60.0
    assert settings.cli_max_steps == 64
    assert settings.cli_poll_interval_seconds == 0.0
    assert settings.cli_event_limit == 100
    assert settings.cli_output_format == "table"
    assert settings.streamlit_api_url == ""
    assert settings.streamlit_resolved_api_url == settings.cli_api_url
    assert settings.streamlit_http_timeout_seconds == 5.0
    assert settings.streamlit_refresh_interval_seconds == 5.0
    assert settings.streamlit_event_limit == 100
    assert settings.streamlit_turn_limit == 100
    assert settings.streamlit_run_limit == 20
    assert settings.streamlit_max_auto_steps == 64
    assert settings.streamlit_auto_advance_interval_seconds == 1.0
    assert settings.streamlit_initial_sidebar_state == "expanded"
    assert settings.streamlit_language == "ja"
    assert settings.streamlit_i18n_file == ""
    assert settings.streamlit_i18n_path is None
    assert settings.streamlit_save_file == Path(".werewolf-agent/streamlit/saves.json")
    assert settings.streamlit_save_file_path == (
        repository_root() / ".werewolf-agent/streamlit/saves.json"
    )
    assert settings.streamlit_page_title == "Werewolf Agent"
    assert settings.streamlit_default_seed == 1
    assert settings.streamlit_default_manual_player_id == "player-1"
    assert settings.streamlit_message_max_chars == 200
    assert settings.streamlit_service_name == "werewolf-agent-streamlit"
    assert settings.api_title == "Werewolf Agent API"
    assert settings.api_service_name == "werewolf-agent-api"
    assert settings.api_version == "0.1.0"
    assert settings.api_debug is False
    assert settings.reveal_api_enabled is True
    assert settings.api_game_list_default_limit == 20
    assert settings.api_game_list_max_limit == 100
    assert settings.api_timeline_default_limit == 100
    assert settings.api_timeline_max_limit == 500
    assert settings.llm_provider == "lmstudio"
    assert settings.model == "auto"
    assert settings.llm_base_url == "http://127.0.0.1:1234/v1"
    assert settings.configured_openai_api_key == ""
    assert settings.llm_prompt_path is None
    assert settings.llm_fake_responses_path is None
    assert settings.llm_players_path is None
    assert settings.cors_allowed_methods_list == ["GET", "POST"]
    assert settings.cors_allowed_headers_list == ["*"]
    assert settings.game_role_name_map["werewolf"] == "人狼"
    assert settings.game_phase_name_map["day_discussion"] == "昼チャット"
    assert settings.game_min_players == DEFAULT_GAME_MIN_PLAYERS
    assert settings.game_max_players == DEFAULT_GAME_MAX_PLAYERS
    assert settings.game_default_player_count == DEFAULT_GAME_DEFAULT_PLAYER_COUNT
    assert settings.game_default_narration_mode == "standard"
    assert settings.game_rules_path is None
    assert settings.game_roles_path is None


def test_game_usecase_config_is_built_from_interface_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        game_min_players=5,
        game_max_players=8,
        game_default_player_count=7,
        game_supported_agent_type="llm",
        game_supported_agent_name="LLM Agent",
        game_default_setup_id="default",
        game_default_setup_name="Custom Rules",
    )

    usecase_config = build_game_usecase_config(settings)

    assert usecase_config.min_players == 5
    assert usecase_config.max_players == 8
    assert usecase_config.default_player_count == 7
    assert usecase_config.supported_agent_type == "llm"
    assert usecase_config.default_setup_id == "default"
    assert usecase_config.default_narration_mode == "standard"
    assert usecase_config.game_list_default_limit == 20
    assert usecase_config.game_list_max_limit == 100
    assert usecase_config.timeline_default_limit == 100
    assert usecase_config.timeline_max_limit == 500

    llm_config = build_llm_provider_config(settings)
    assert llm_config.provider == "lmstudio"
    assert llm_config.model == "auto"
    assert llm_config.base_url == "http://127.0.0.1:1234/v1"
    assert llm_config.api_key == "lm-studio"
    assert llm_config.timeout_seconds == 12.0
    assert llm_config.max_retries == 0
    assert llm_config.max_tokens == 96
    assert llm_config.temperature == 0.7

    game_definitions = build_game_definitions(settings)
    assert sorted(game_definitions.roles.roles) == ["knight", "seer", "villager", "werewolf"]
    assert game_definitions.roles.default_counts_for(5) == {
        "werewolf": 1,
        "seer": 1,
        "knight": 1,
        "villager": 2,
    }

    llm_definitions = build_llm_definitions(settings)
    names = [profile.name for profile in llm_definitions.players.players.values()]
    assert len(names) >= 8
    assert len(set(names)) == len(names)
    assert all(" " not in name for name in names)
    assert llm_definitions.prompt.response_format["schema"] == "AgentDecision"


def test_lmstudio_llm_provider_config_is_built_from_settings() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider="lmstudio",
        model="local-model",
        llm_base_url="http://127.0.0.1:1234/v1",
        llm_timeout_seconds=45,
        llm_max_retries=3,
        llm_max_tokens=128,
        llm_temperature=0.2,
    )

    llm_config = build_llm_provider_config(settings)

    assert llm_config.provider == "lmstudio"
    assert llm_config.model == "local-model"
    assert llm_config.base_url == "http://127.0.0.1:1234/v1"
    assert llm_config.api_key == "lm-studio"
    assert llm_config.timeout_seconds == 45.0
    assert llm_config.max_retries == 3
    assert llm_config.max_tokens == 128
    assert llm_config.temperature == 0.2
    assert "lm-studio" not in repr(llm_config)


def test_openai_llm_provider_config_uses_secret_api_key() -> None:
    settings = AppSettings(
        _env_file=None,
        llm_provider="openai",
        model="gpt-4.1-mini",
        openai_api_key="sk-test",
    )

    llm_config = build_llm_provider_config(settings)

    assert llm_config.provider == "openai"
    assert llm_config.model == "gpt-4.1-mini"
    assert llm_config.base_url == ""
    assert llm_config.api_key == "sk-test"
    assert llm_config.max_tokens == 96
    assert "sk-test" not in repr(llm_config)


def test_llm_provider_settings_validate_required_values() -> None:
    AppSettings(_env_file=None, llm_provider="fake")

    with pytest.raises(ValidationError, match="WEREWOLF_LLM_BASE_URL"):
        AppSettings(_env_file=None, llm_provider="lmstudio", llm_base_url="")

    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        AppSettings(_env_file=None, llm_provider="openai")


def test_game_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEREWOLF_GAME_MIN_PLAYERS", "5")
    monkeypatch.setenv("WEREWOLF_GAME_MAX_PLAYERS", "8")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_PLAYER_COUNT", "7")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_TYPE", "llm")
    monkeypatch.setenv("WEREWOLF_GAME_SUPPORTED_AGENT_NAME", "Configurable LLM Agent")
    monkeypatch.setenv("WEREWOLF_LLM_PROVIDER", "lmstudio")
    monkeypatch.setenv("WEREWOLF_MODEL", "local-model")
    monkeypatch.setenv("WEREWOLF_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("WEREWOLF_LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("WEREWOLF_LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("WEREWOLF_LLM_MAX_TOKENS", "128")
    monkeypatch.setenv("WEREWOLF_LLM_TEMPERATURE", "0.2")
    monkeypatch.setenv(
        "WEREWOLF_LLM_PROMPT_FILE",
        "backend/src/werewolf_agent/resources/prompts/agent_decision.toml",
    )
    monkeypatch.setenv(
        "WEREWOLF_LLM_FAKE_RESPONSES_FILE",
        "backend/src/werewolf_agent/resources/llm/fake_responses.toml",
    )
    monkeypatch.setenv(
        "WEREWOLF_LLM_PLAYERS_FILE",
        "backend/src/werewolf_agent/resources/llm/players.toml",
    )
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_SETUP_ID", "custom")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_SETUP_NAME", "Custom Rules")
    monkeypatch.setenv(
        "WEREWOLF_GAME_RULES_FILE",
        "backend/src/werewolf_agent/resources/game/rules.toml",
    )
    monkeypatch.setenv(
        "WEREWOLF_GAME_ROLES_FILE",
        "backend/src/werewolf_agent/resources/game/roles.toml",
    )
    monkeypatch.setenv("WEREWOLF_GAME_SETUP_DESCRIPTION_TEMPLATE", "{min_players}-{max_players}")
    monkeypatch.setenv("WEREWOLF_GAME_ROLE_NAMES", "villager:Villager")
    monkeypatch.setenv("WEREWOLF_GAME_PHASE_NAMES", "night:Night")
    monkeypatch.setenv("WEREWOLF_CLI_API_URL", "http://api.test/api/v1")
    monkeypatch.setenv("WEREWOLF_ADVANCE_JOB_POLL_INTERVAL_SECONDS", "0.1")
    monkeypatch.setenv("WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("WEREWOLF_CLI_OUTPUT_FORMAT", "json")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_API_URL", "http://ui-api.test/api/v1")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_HTTP_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_REFRESH_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_EVENT_LIMIT", "50")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_TURN_LIMIT", "40")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_RUN_LIMIT", "9")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_LANGUAGE", "en")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_I18N_FILE", "tmp/streamlit/i18n.toml")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_SAVE_FILE", "tmp/streamlit/saves.json")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_MAX_AUTO_STEPS", "12")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_INITIAL_SIDEBAR_STATE", "collapsed")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_PAGE_TITLE", "Werewolf Console")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_DEFAULT_SEED", "33")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_DEFAULT_MANUAL_PLAYER_ID", "player-2")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_MESSAGE_MAX_CHARS", "120")
    monkeypatch.setenv("WEREWOLF_STREAMLIT_SERVICE_NAME", "test-streamlit")
    monkeypatch.setenv("WEREWOLF_API_SERVICE_NAME", "test-api")
    monkeypatch.setenv("WEREWOLF_REVEAL_API_ENABLED", "false")
    monkeypatch.setenv("WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT", "7")
    monkeypatch.setenv("WEREWOLF_API_GAME_LIST_MAX_LIMIT", "77")
    monkeypatch.setenv("WEREWOLF_API_TIMELINE_DEFAULT_LIMIT", "17")
    monkeypatch.setenv("WEREWOLF_API_TIMELINE_MAX_LIMIT", "177")
    monkeypatch.setenv("WEREWOLF_GAME_DEFAULT_NARRATION_MODE", "rich")

    settings = AppSettings(_env_file=None)

    assert settings.game_min_players == 5
    assert settings.game_max_players == 8
    assert settings.game_default_player_count == 7
    assert settings.game_supported_agent_type == "llm"
    assert settings.game_supported_agent_name == "Configurable LLM Agent"
    assert settings.llm_provider == "lmstudio"
    assert settings.model == "local-model"
    assert settings.llm_base_url == "http://127.0.0.1:1234/v1"
    assert settings.llm_timeout_seconds == 45.0
    assert settings.llm_max_retries == 3
    assert settings.llm_max_tokens == 128
    assert settings.llm_temperature == 0.2
    assert (
        settings.llm_prompt_path
        == repository_root() / "backend/src/werewolf_agent/resources/prompts/agent_decision.toml"
    )
    assert (
        settings.llm_fake_responses_path
        == repository_root() / "backend/src/werewolf_agent/resources/llm/fake_responses.toml"
    )
    assert (
        settings.llm_players_path
        == repository_root() / "backend/src/werewolf_agent/resources/llm/players.toml"
    )
    assert settings.game_default_setup_id == "custom"
    assert settings.game_default_setup_name == "Custom Rules"
    assert (
        settings.game_rules_path
        == repository_root() / "backend/src/werewolf_agent/resources/game/rules.toml"
    )
    assert (
        settings.game_roles_path
        == repository_root() / "backend/src/werewolf_agent/resources/game/roles.toml"
    )
    assert settings.game_setup_description_template == "{min_players}-{max_players}"
    assert settings.game_role_name_map == {"villager": "Villager"}
    assert settings.game_phase_name_map == {"night": "Night"}
    assert settings.cli_api_url == "http://api.test/api/v1"
    assert settings.advance_job_poll_interval_seconds == 0.1
    assert settings.advance_job_poll_timeout_seconds == 30.0
    assert settings.cli_output_format == "json"
    assert settings.streamlit_api_url == "http://ui-api.test/api/v1"
    assert settings.streamlit_resolved_api_url == "http://ui-api.test/api/v1"
    assert settings.streamlit_http_timeout_seconds == 5.0
    assert settings.streamlit_refresh_interval_seconds == 2.0
    assert settings.streamlit_event_limit == 50
    assert settings.streamlit_turn_limit == 40
    assert settings.streamlit_run_limit == 9
    assert settings.streamlit_max_auto_steps == 12
    assert settings.streamlit_auto_advance_interval_seconds == 0.5
    assert settings.streamlit_initial_sidebar_state == "collapsed"
    assert settings.streamlit_language == "en"
    assert settings.streamlit_i18n_path == repository_root() / "tmp/streamlit/i18n.toml"
    assert settings.streamlit_save_file_path == repository_root() / "tmp/streamlit/saves.json"
    assert settings.streamlit_page_title == "Werewolf Console"
    assert settings.streamlit_default_seed == 33
    assert settings.streamlit_default_manual_player_id == "player-2"
    assert settings.streamlit_message_max_chars == 120
    assert settings.streamlit_service_name == "test-streamlit"
    assert settings.api_service_name == "test-api"
    assert settings.reveal_api_enabled is False
    assert settings.api_game_list_default_limit == 7
    assert settings.api_game_list_max_limit == 77
    assert settings.api_timeline_default_limit == 17
    assert settings.api_timeline_max_limit == 177
    assert settings.game_default_narration_mode == "rich"


def test_definition_values_load_through_runtime_settings(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.toml"
    roles_file = tmp_path / "roles.toml"
    players_file = tmp_path / "players.toml"
    prompt_file = tmp_path / "prompt.toml"
    fake_responses_file = tmp_path / "fake_responses.toml"

    rules_file.write_text(
        """
[local_rules]
day_speech_limit_per_player = 1
allow_self_vote = false
allow_vote_revision = false
allow_night_action_revision = false
enable_first_night_attack = true
enable_no_elimination_on_tie = true
enable_random_elimination_on_tie = false
allow_knight_self_guard = true
allow_knight_repeat_guard = true
allow_seer_self_inspect = false
allow_werewolf_friendly_fire = false
reveal_role_on_death = false
""".strip(),
        encoding="utf-8",
    )
    roles_file.write_text(
        """
[roles.plain]
faction = "village"
abilities = []

[roles.beast]
faction = "werewolf"
abilities = ["night_attack", "pack_knowledge"]

[default_role_counts.5]
beast = 1
plain = 4
""".strip(),
        encoding="utf-8",
    )
    players_file.write_text(
        """
[players.quiet]
enabled = true
name = "Quiet"
age = 30
gender = "Unspecified"
personality = "Careful"
speaking_style = "Short"
reasoning_style = "Evidence first"
risk_tolerance = "low"
""".strip(),
        encoding="utf-8",
    )
    prompt_file.write_text(
        """
name = "test"
version = 1
alias = "local"
input_variables = ["player_id"]
response_format = { schema = "AgentDecision" }
[[messages]]
role = "human"
content = "{{player_id}}"
""".strip(),
        encoding="utf-8",
    )
    fake_responses_file.write_text(
        """
name = "test"
version = 1
alias = "local"
[templates]
pass = '{"type":"pass","player_id":"$player_id","reason":"fallback"}'
""".strip(),
        encoding="utf-8",
    )

    settings = AppSettings(
        _env_file=None,
        game_min_players=5,
        game_max_players=5,
        game_default_player_count=5,
        game_rules_file=str(rules_file),
        game_roles_file=str(roles_file),
        llm_players_file=str(players_file),
        llm_prompt_file=str(prompt_file),
        llm_fake_responses_file=str(fake_responses_file),
    )

    assert settings.game_definitions.roles.default_counts_for(5) == {
        "beast": 1,
        "plain": 4,
    }
    assert sorted(settings.llm_definitions.players.players) == ["quiet"]
    assert settings.llm_definitions.prompt.name == "test"


def test_invalid_definition_values_fail_in_runtime_settings(tmp_path: Path) -> None:
    roles_file = tmp_path / "roles.toml"
    roles_file.write_text(
        """
[roles.plain]
faction = "village"
abilities = []

[default_role_counts.5]
missing = 5
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="unknown roles"):
        AppSettings(
            _env_file=None,
            game_min_players=5,
            game_max_players=5,
            game_default_player_count=5,
            game_roles_file=str(roles_file),
        )


def test_missing_local_rule_flags_fail_during_settings_load(tmp_path: Path) -> None:
    rules_file = tmp_path / "rules.toml"
    rules_file.write_text(
        """
[local_rules]
enable_no_elimination_on_tie = true
enable_random_elimination_on_tie = false
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="day_speech_limit_per_player"):
        AppSettings(
            _env_file=None,
            game_rules_file=str(rules_file),
        )


def test_missing_default_role_counts_fail_during_settings_load(tmp_path: Path) -> None:
    roles_file = tmp_path / "roles.toml"
    roles_file.write_text(
        """
[roles.plain]
faction = "village"
abilities = []

[roles.beast]
faction = "werewolf"
abilities = ["night_attack", "pack_knowledge"]

[default_role_counts.5]
beast = 1
plain = 4
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="6"):
        AppSettings(
            _env_file=None,
            game_min_players=5,
            game_max_players=6,
            game_default_player_count=5,
            game_roles_file=str(roles_file),
        )


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
        AppSettings(_env_file=None, game_setup_description_template="{unknown}")


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
        ("streamlit_initial_sidebar_state", "hidden"),
        ("game_supported_agent_type", "bot"),
        ("game_default_narration_mode", "verbose"),
        ("llm_provider", "anthropic"),
    ],
)
def test_choice_settings_reject_invalid_values(field_name: str, value: str) -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, **{field_name: value})


def test_api_page_limit_settings_reject_inconsistent_defaults() -> None:
    with pytest.raises(ValidationError, match="api_game_list_default_limit"):
        AppSettings(
            _env_file=None,
            api_game_list_default_limit=101,
            api_game_list_max_limit=100,
        )

    with pytest.raises(ValidationError, match="api_timeline_default_limit"):
        AppSettings(
            _env_file=None,
            api_timeline_default_limit=501,
            api_timeline_max_limit=500,
        )


def test_log_file_name_rejects_paths() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, log_file_name="../app.jsonl")
