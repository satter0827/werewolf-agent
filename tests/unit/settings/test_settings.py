from werewolf_agent.settings import AppSettings


def test_runtime_settings_do_not_own_game_definition_defaults() -> None:
    settings = AppSettings(_env_file=None)

    assert not hasattr(settings, "game_default_setup_preset_id")
    assert not hasattr(settings, "game_default_player_count")
    assert not hasattr(settings, "llm_players_file")
    assert not hasattr(settings, "streamlit_default_manual_player_id")
