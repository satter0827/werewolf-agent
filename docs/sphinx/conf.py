"""Sphinx configuration for Werewolf Agent documentation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

project = "Werewolf Agent"
author = "werewolf-agent contributors"
release = "0.1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
root_doc = "sphinx/index"
exclude_patterns = ["sphinx/_build"]

autosummary_generate = True
autodoc_typehints = "description"
autodoc_member_order = "bysource"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

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
