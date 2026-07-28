"""Sphinx configuration for Werewolf Agent documentation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from werewolf_agent import __version__  # noqa: E402

project = "Werewolf Agent"
author = "werewolf-agent contributors"
release = __version__

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_generated/**", "AGENTS.md"]
nitpicky = True
language = "ja"
html_search_language = "ja"
myst_enable_extensions = ["colon_fence"]

autodoc_typehints = "description"
autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

html_theme = "furo"
html_title = "Werewolf Agent"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "light_css_variables": {
        "color-background-primary": "#fffdf8",
        "color-background-secondary": "#f6f3ec",
        "color-foreground-primary": "#17243a",
        "color-foreground-secondary": "#647083",
        "color-brand-primary": "#263a5b",
        "color-brand-content": "#315f9f",
    },
    "navigation_with_keys": True,
    "top_of_page_buttons": ["view"],
}

copybutton_prompt_text = r">>> |\.\.\. |PS [^>]*> |\$ "
copybutton_prompt_is_regexp = True

_THEME_TRANSLATIONS = {
    "On this page": "このページ内",
    "View this page": "ページのソースを表示",
}


def _localize_theme_labels(app, pagename, templatename, context, doctree) -> None:
    """Furo固有の表示文言をSphinxの日本語UIへ揃える。"""
    del pagename, templatename, doctree
    translate = context.get("_", app.translator.gettext)
    context["_"] = lambda message: _THEME_TRANSLATIONS.get(message, translate(message))


def setup(app) -> None:
    """文書themeの日本語表示を登録する。"""
    app.connect("html-page-context", _localize_theme_labels)
