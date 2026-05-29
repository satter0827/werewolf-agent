"""Sphinx configuration for Werewolf Agent documentation."""

from __future__ import annotations

project = "Werewolf Agent"
author = "werewolf-agent contributors"
release = "0.1.0"

extensions = ["myst_parser"]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
root_doc = "sphinx/index"
exclude_patterns = ["sphinx/_build"]

html_theme = "alabaster"
html_title = "Werewolf Agent Docs"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "description": "LLM agents on a deterministic Werewolf backend",
    "fixed_sidebar": True,
    "page_width": "1080px",
    "sidebar_width": "280px",
}
