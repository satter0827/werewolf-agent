"""Streamlit styling adapter."""

from __future__ import annotations

from werewolf_agent.commons.configuration import AppSettings
from werewolf_agent.commons.resources import load_streamlit_css


def load_style_tag(settings: AppSettings) -> str:
    """Load configured Streamlit CSS and return a style tag."""
    return style_tag(load_streamlit_css(settings.streamlit_css_path))


def style_tag(css: str) -> str:
    """Wrap trusted Streamlit CSS in a style tag."""
    return f"<style>\n{css.strip()}\n</style>"
