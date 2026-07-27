"""Streamlit AppTestによる縮退起動画面の安全性。"""

from contextlib import nullcontext
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from werewolf_agent.clients.streamlit.setup import (
    VIEW_APP_SETTINGS,
    VIEW_GAME_SETTINGS,
    VIEW_HISTORY,
    VIEW_PLAY_SETUP,
)
from werewolf_agent.clients.streamlit.views import runtime
from werewolf_agent.contracts.api import SessionResponse
from werewolf_agent.settings import AppSettings


def test_streamlit_renders_safe_degraded_shell_without_crashing(monkeypatch) -> None:
    monkeypatch.setenv("WEREWOLF_SUPABASE_URL", "")
    monkeypatch.setenv("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", "")
    app = Path("src/werewolf_agent/clients/streamlit/app.py")

    result = AppTest.from_file(str(app)).run(timeout=20)

    assert not result.exception
    assert result.warning or result.info
    rendered = " ".join(message.value for message in (*result.warning, *result.info))
    assert "ログインを一時的に利用できません" in rendered
    assert "token" not in rendered.casefold()
    assert "password" not in rendered.casefold()


@pytest.mark.parametrize(
    ("view", "renderer_name", "title"),
    [
        (VIEW_PLAY_SETUP, "_render_setup_screen", "Play integration"),
        (VIEW_GAME_SETTINGS, "_render_game_settings_screen", "Setup integration"),
        (VIEW_HISTORY, "_render_history_screen", "Records integration"),
        (VIEW_APP_SETTINGS, "_render_settings_screen", "Preferences integration"),
    ],
)
def test_streamlit_routes_authenticated_workspaces_through_the_real_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    view: str,
    renderer_name: str,
    title: str,
) -> None:
    """Entry pointから認証境界とworkspace routingを通して主要画面を選択する。"""
    settings = AppSettings(
        _env_file=None,
        supabase_url="http://127.0.0.1:54321",
        supabase_publishable_key="publishable-test",
    )
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "configure_entrypoint_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime, "log_streamlit_rerun_started", lambda _settings: None)
    monkeypatch.setattr(runtime, "require_supabase_client_config", lambda _settings: None)
    monkeypatch.setattr(runtime, "ensure_session", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "bind_session", lambda _session: nullcontext())
    monkeypatch.setattr(
        runtime,
        "load_session",
        lambda **kwargs: SessionResponse(
            anonymous=True,
            administrator=False,
            llm_mode="fake",
        ),
    )
    monkeypatch.setattr(runtime, "load_runtime_status", lambda **kwargs: None)
    monkeypatch.setattr(runtime, "_component_available", lambda *args, **kwargs: True)
    monkeypatch.setattr(runtime, "_render_sidebar", lambda *args, **kwargs: (None, view))
    monkeypatch.setattr(
        runtime,
        renderer_name,
        lambda st, *args, **kwargs: st.title(title),
    )

    result = AppTest.from_file("src/werewolf_agent/clients/streamlit/app.py").run(timeout=20)

    assert not result.exception
    assert [item.value for item in result.title] == [title]
