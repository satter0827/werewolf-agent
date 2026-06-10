from typing import Any

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.entrypoint.streamlit import app
from werewolf_agent.entrypoint.streamlit.i18n import load_i18n
from werewolf_agent.entrypoint.streamlit.screens import ScreenCatalog, load_screen_catalog


def test_sidebar_navigation_order_is_play_observe_history_settings(monkeypatch) -> None:
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)
    screens = load_screen_catalog(settings)
    streamlit = _StreamlitStub()

    monkeypatch.setattr(app, "_render_sidebar_brand", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_history_selector", lambda *args, **kwargs: None)

    app._render_sidebar(streamlit, settings, catalog=catalog, lang="ja", screens=screens)

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

    app._render_sidebar(streamlit, settings, catalog=catalog, lang="ja", screens=screens)

    assert streamlit.sidebar.button_labels == ["▶ プレイ", "◉ 観戦", "▣ 履歴", "⚙ 設定"]


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
