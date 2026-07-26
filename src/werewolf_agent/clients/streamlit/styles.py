"""Streamlit styling adapter."""

from __future__ import annotations

from werewolf_agent.adapters.resources import load_streamlit_css
from werewolf_agent.settings import AppSettings


def load_style_tag(settings: AppSettings, *, information_density: str = "comfortable") -> str:
    """Load configured Streamlit CSS and return a style tag."""
    return style_tag(
        load_streamlit_css(
            settings.streamlit_css_path,
            runtime_css=_density_css(information_density),
        )
    )


def style_tag(css: str) -> str:
    """Wrap trusted Streamlit CSS in a style tag."""
    return f"<style>\n{css.strip()}\n</style>"


def _density_css(information_density: str) -> str:
    spacing = "0.7rem" if information_density == "compact" else "1rem"
    section_spacing = "0.85rem" if information_density == "compact" else "1.25rem"
    return (
        ":root {\n"
        f"    --wa-density-block-gap: {spacing};\n"
        f"    --wa-density-section-gap: {section_spacing};\n"
        "}"
    )
