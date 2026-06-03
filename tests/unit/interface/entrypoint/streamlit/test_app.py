from typing import Any

from werewolf_agent.interface.entrypoint.streamlit import app
from werewolf_agent.interface.entrypoint.streamlit.i18n import load_i18n
from werewolf_agent.interface.runtime import AppSettings


def test_sidebar_navigation_order_is_play_observe_settings(monkeypatch) -> None:
    settings = AppSettings(_env_file=None)
    catalog = load_i18n(settings)
    streamlit = _StreamlitStub()

    monkeypatch.setattr(app, "_render_sidebar_brand", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_render_save_selector", lambda *args, **kwargs: None)

    app._render_sidebar(streamlit, settings, catalog=catalog, lang="ja")

    assert streamlit.sidebar.button_labels == ["▶ プレイ", "◉ 観戦", "⚙ 設定"]


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
