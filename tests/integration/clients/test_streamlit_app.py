"""Streamlit AppTestによる縮退起動画面の安全性。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_renders_safe_degraded_shell_without_crashing(monkeypatch) -> None:
    monkeypatch.setenv("WEREWOLF_SUPABASE_URL", "")
    monkeypatch.setenv("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", "")
    app = Path("src/werewolf_agent/clients/streamlit/app.py")

    result = AppTest.from_file(str(app)).run(timeout=20)

    assert not result.exception
    assert result.warning or result.info
    rendered = " ".join(message.value for message in (*result.warning, *result.info))
    assert "認証を利用できません" in rendered
    assert "token" not in rendered.casefold()
    assert "password" not in rendered.casefold()
