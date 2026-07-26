from pathlib import Path

from werewolf_agent.adapters.resources import load_streamlit_css
from werewolf_agent.clients.streamlit.styles import load_style_tag, style_tag
from werewolf_agent.settings import AppSettings


def test_streamlit_css_loader_reads_packaged_default() -> None:
    css = load_streamlit_css(None)

    assert "--wa-shell" in css
    assert ".wa-status-grid" in css
    assert "<style>" not in css


def test_streamlit_css_loader_uses_external_override(tmp_path: Path) -> None:
    css_file = tmp_path / "streamlit.css"
    css_file.write_text(".custom-screen { color: red; }", encoding="utf-8")
    settings = AppSettings(_env_file=None, streamlit_css_file=str(css_file))

    tag = load_style_tag(settings)
    assert "--wa-shell" in tag
    assert tag.index("--wa-shell") < tag.index(".custom-screen")
    assert tag.endswith(".custom-screen { color: red; }\n</style>")


def test_runtime_density_values_precede_external_override(tmp_path: Path) -> None:
    css_file = tmp_path / "streamlit.css"
    css_file.write_text(":root { --wa-density-block-gap: 2rem; }", encoding="utf-8")
    settings = AppSettings(_env_file=None, streamlit_css_file=str(css_file))

    tag = load_style_tag(settings, information_density="compact")

    assert "--wa-density-block-gap: 0.7rem" in tag
    assert tag.index("--wa-density-block-gap: 0.7rem") < tag.rindex("--wa-density-block-gap: 2rem")


def test_style_tag_wraps_trusted_css_without_default_fallback() -> None:
    assert style_tag("body { color: black; }") == "<style>\nbody { color: black; }\n</style>"
