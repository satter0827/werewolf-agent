from werewolf_agent.clients.streamlit.resources import load_css
from werewolf_agent.clients.streamlit.styles import load_style_tag, style_tag


def test_streamlit_css_is_packaged_and_token_driven() -> None:
    css = load_css()

    assert "--wa-page: #f6f3ec" in css
    assert "--wa-space-6: 1.5rem" in css
    assert ".wa-status-grid" in css
    assert ".wa-seat-grid" in css
    assert "gradient(" not in css
    assert "<style>" not in css


def test_style_tag_uses_only_packaged_css() -> None:
    tag = load_style_tag()

    assert tag.startswith("<style>\n")
    assert tag.endswith("\n</style>")
    assert "--wa-control-min: 2.75rem" in tag


def test_style_tag_wraps_trusted_css() -> None:
    assert style_tag("body { color: black; }") == "<style>\nbody { color: black; }\n</style>"
