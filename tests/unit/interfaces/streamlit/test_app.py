import logging
from typing import Any

from werewolf_agent.configuration import AppSettings
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import LocalRulesSettings
from werewolf_agent.interfaces.streamlit import app
from werewolf_agent.interfaces.streamlit.i18n import load_i18n
from werewolf_agent.interfaces.streamlit.screens import ScreenCatalog, load_screen_catalog


def test_sidebar_navigation_order_is_play_observe_history_settings(monkeypatch) -> None:
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)
    screens = load_screen_catalog(settings)
    streamlit = _StreamlitStub()

    monkeypatch.setattr(app, "_render_sidebar_brand", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_history_selector", lambda *args, **kwargs: None)

    app._render_sidebar(
        streamlit,
        settings,
        catalog=catalog,
        lang="ja",
        screens=screens,
    )

    assert streamlit.sidebar.button_labels == ["▶ プレイ", "◉ 観戦", "▣ 履歴", "⚙ 設定"]


def test_sidebar_disabled_element_does_not_call_renderer(monkeypatch) -> None:
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)
    screens = _sidebar_catalog(brand_enabled=False)
    streamlit = _StreamlitStub()

    monkeypatch.setattr(
        app,
        "_render_sidebar_brand",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("brand renderer called")),
    )

    app._render_sidebar(
        streamlit,
        settings,
        catalog=catalog,
        lang="ja",
        screens=screens,
    )

    assert streamlit.sidebar.button_labels == ["▶ プレイ", "◉ 観戦", "▣ 履歴", "⚙ 設定"]


def test_app_does_not_block_game_views_for_anonymous_session(monkeypatch) -> None:
    settings = AppSettings(
        _env_file=None,
        supabase_url="http://127.0.0.1:54321",
        supabase_publishable_key="publishable-test",
    )
    streamlit = _AppStub()
    rendered: list[str] = []

    monkeypatch.setattr(app, "require_supabase_client_config", lambda _settings: None)
    monkeypatch.setattr(app, "ensure_session", lambda _settings, **_kwargs: object())
    monkeypatch.setattr(
        app,
        "_render_sidebar",
        lambda *args, **kwargs: (None, app.VIEW_PLAY_SETUP),
    )
    monkeypatch.setattr(
        app,
        "_render_setup_screen",
        lambda *args, **kwargs: rendered.append("setup"),
    )
    monkeypatch.setattr(app, "_render_history_screen", _fail_renderer("history"))

    app._render_app(streamlit, settings)

    assert rendered == ["setup"]


def test_app_shows_supabase_config_error_before_rendering_game_views(
    monkeypatch,
    caplog,
) -> None:
    settings = AppSettings(_env_file=None)
    streamlit = _AppStub()

    monkeypatch.setattr(app, "_render_sidebar", _fail_renderer("sidebar"))
    monkeypatch.setattr(app, "_render_setup_screen", _fail_renderer("setup"))

    with caplog.at_level(logging.INFO, logger=app.__name__):
        app._render_app(streamlit, settings)

    assert streamlit.error_texts == [
        (
            "WEREWOLF_SUPABASE_URL and WEREWOLF_SUPABASE_PUBLISHABLE_KEY are required. "
            "Create .env from local Supabase values before starting CLI or Streamlit."
        )
    ]
    records = [
        record
        for record in caplog.records
        if record.event_action == "streamlit.application_error.handled"
    ]
    assert len(records) == 1
    assert records[0].event_outcome == "failure"
    assert records[0].error_message == streamlit.error_texts[0]


def test_create_game_logs_operational_error(monkeypatch, caplog) -> None:
    settings = AppSettings(_env_file=None)
    streamlit = _StreamlitStub()
    feedback = _FeedbackStub()
    catalog = load_i18n(settings)

    def fail_create_game(*args: object, **kwargs: object) -> object:
        raise AppError("operation request timed out", code=ErrorCode.API_UNAVAILABLE)

    monkeypatch.setattr(app, "create_game_from_setup", fail_create_game)

    with caplog.at_level(logging.INFO, logger=app.__name__):
        app._create_game(
            streamlit,
            feedback=feedback,
            settings=settings,
            role_counts={"werewolf": 1, "villager": 4},
            rules=_rules(),
            seed_text="1",
            manual_player_id="player-1",
            screen_mode="play",
            catalog=catalog,
            lang="ja",
        )

    assert feedback.error_texts == ["operation request timed out"]
    records = [
        record for record in caplog.records if record.event_action == "streamlit.game.create_failed"
    ]
    assert len(records) == 1
    assert records[0].event_outcome == "failure"
    assert records[0].error_message == "operation request timed out"
    assert records[0].screen_mode == "play"


def _fail_renderer(name: str):
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"{name} renderer called")

    return fail


def _sidebar_catalog(*, brand_enabled: bool) -> ScreenCatalog:
    return ScreenCatalog.model_validate(
        {
            "sidebar": {
                "regions": {
                    "main": {
                        "elements": [
                            {"id": "brand", "order": 10, "enabled": brand_enabled},
                            {"id": "navigation", "order": 20, "enabled": True},
                        ]
                    }
                }
            },
            "setup": {
                "layout": {"summary_columns": 3, "seed_columns": 2},
                "regions": {
                    "main": {"elements": []},
                    "summary": {"elements": []},
                    "action": {"elements": []},
                },
            },
            "settings": {"regions": {"tabs": {"elements": []}}},
            "game": {
                "layout": {"columns": [1.55, 1.0], "next_action_columns": 4},
                "regions": {
                    "top": {"elements": []},
                    "main": {"elements": []},
                    "side": {"elements": []},
                    "bottom": {"elements": []},
                },
            },
        }
    )


def _rules() -> LocalRulesSettings:
    return LocalRulesSettings(
        day_speech_limit_per_player=1,
        allow_self_vote=False,
        allow_vote_revision=False,
        allow_night_action_revision=False,
        enable_first_night_attack=True,
        enable_no_elimination_on_tie=True,
        enable_random_elimination_on_tie=False,
        allow_knight_self_guard=True,
        allow_knight_repeat_guard=True,
        allow_seer_self_inspect=False,
        allow_werewolf_friendly_fire=False,
        reveal_role_on_death=False,
    )


class _SidebarStub:
    def __init__(self) -> None:
        self.button_labels: list[str] = []

    def divider(self) -> None:
        pass

    def subheader(self, value: str) -> None:
        pass

    def button(self, label: str, **kwargs: Any) -> bool:
        self.button_labels.append(label)
        return False


class _StreamlitStub:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.sidebar = _SidebarStub()

    def rerun(self) -> None:
        raise AssertionError("rerun should not be called when no button is clicked")


class _AppStub(_StreamlitStub):
    def __init__(self) -> None:
        super().__init__()
        self.error_texts: list[str] = []
        self.header_texts: list[str] = []
        self.info_texts: list[str] = []

    def set_page_config(self, **kwargs: Any) -> None:
        pass

    def markdown(self, value: str, **kwargs: Any) -> None:
        pass

    def header(self, value: str) -> None:
        self.header_texts.append(value)

    def error(self, value: str) -> None:
        self.error_texts.append(value)

    def info(self, value: str) -> None:
        self.info_texts.append(value)


class _FeedbackStub:
    def __init__(self) -> None:
        self.error_texts: list[str] = []

    def error(self, value: str) -> None:
        self.error_texts.append(value)
