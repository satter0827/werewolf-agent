"""Streamlit styling adapter."""

from __future__ import annotations

from werewolf_agent.clients.streamlit.resources import load_css


def load_style_tag() -> str:
    """Load the client-owned Streamlit CSS and return a style tag."""
    return style_tag(load_css())


def style_tag(css: str) -> str:
    """Wrap trusted Streamlit CSS in a style tag."""
    return f"<style>\n{css.strip()}\n</style>"
