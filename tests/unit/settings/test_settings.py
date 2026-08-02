import pytest

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


def test_paid_llm_is_disabled_by_default() -> None:
    """有料providerはworkerで明示許可するまで使用しない。"""
    settings = AppSettings(_env_file=None)

    assert settings.worker_paid_llm_enabled is False


def test_paid_llm_admission_ttl_must_outlive_heartbeat() -> None:
    """処理中reservationが最初のheartbeat前に失効する設定を拒否する。"""
    with pytest.raises(ValueError, match="admission_ttl_seconds"):
        AppSettings(
            _env_file=None,
            supabase_worker_heartbeat_seconds=20,
            worker_paid_llm_admission_ttl_seconds=20,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"worker_paid_llm_provider": "fake"}, "external provider"),
        (
            {"worker_paid_llm_provider": "lmstudio", "worker_paid_llm_base_url": ""},
            "PAID_LLM_BASE_URL",
        ),
        ({"worker_paid_llm_provider": "openai"}, "OPENAI_API_KEY"),
    ],
)
def test_enabled_paid_llm_requires_complete_external_provider_settings(
    overrides: dict[str, str],
    message: str,
) -> None:
    """予算予約後に設定不足で失敗する構成を起動前に拒否する。"""
    with pytest.raises(ValueError, match=message):
        AppSettings(_env_file=None, worker_paid_llm_enabled=True, **overrides)
