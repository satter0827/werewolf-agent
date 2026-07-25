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
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

source_suffix = {".md": "markdown"}
root_doc = "index"
exclude_patterns = ["_generated/**"]
nitpicky = True

autodoc_typehints = "description"
autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

html_theme = "alabaster"
html_title = "Werewolf Agent"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "description": "Deterministic Werewolf backend for LLM agents",
    "fixed_sidebar": True,
    "page_width": "1080px",
    "sidebar_width": "280px",
}
