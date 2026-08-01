from werewolf_agent.settings import AppSettings


def test_runtime_settings_do_not_own_game_definition_defaults() -> None:
    settings = AppSettings(_env_file=None)

    assert not hasattr(settings, "game_default_setup_preset_id")
    assert not hasattr(settings, "game_default_player_count")
    assert not hasattr(settings, "llm_players_file")
    assert not hasattr(settings, "streamlit_default_manual_player_id")


def test_reveal_api_is_disabled_by_default() -> None:
    """秘密状態の公開は明示設定がなければ無効にする。"""
    settings = AppSettings(_env_file=None)

    assert settings.reveal_api_enabled is False
