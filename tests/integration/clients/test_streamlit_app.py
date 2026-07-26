"""Streamlit AppTestによる起動失敗画面の安全性。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_renders_safe_configuration_error_without_crashing(monkeypatch) -> None:
    monkeypatch.delenv("WEREWOLF_SUPABASE_URL", raising=False)
    monkeypatch.delenv("WEREWOLF_SUPABASE_PUBLISHABLE_KEY", raising=False)
    app = Path("src/werewolf_agent/clients/streamlit/app.py")

    result = AppTest.from_file(str(app)).run(timeout=20)

    assert not result.exception
    assert result.error
    rendered = " ".join(error.value for error in result.error)
    assert "token" not in rendered.casefold()
    assert "password" not in rendered.casefold()
