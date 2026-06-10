from pathlib import Path

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.commons.resources import load_streamlit_css
from werewolf_agent.entrypoint.streamlit.styles import load_style_tag, style_tag


def test_streamlit_css_loader_reads_packaged_default() -> None:
    css = load_streamlit_css(None)

    assert "--wa-shell" in css
    assert ".wa-status-grid" in css
    assert "<style>" not in css


def test_streamlit_css_loader_uses_external_override(tmp_path: Path) -> None:
    css_file = tmp_path / "streamlit.css"
    css_file.write_text(".custom-screen { color: red; }", encoding="utf-8")
    settings = AppSettings(_env_file=None, streamlit_css_file=str(css_file))

    assert load_style_tag(settings) == "<style>\n.custom-screen { color: red; }\n</style>"


def test_style_tag_wraps_trusted_css_without_default_fallback() -> None:
    assert style_tag("body { color: black; }") == "<style>\nbody { color: black; }\n</style>"
