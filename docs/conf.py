"""Sphinx configuration for Werewolf Agent documentation."""

from __future__ import annotations

import inspect
import operator
import sys
import types
from functools import reduce
from pathlib import Path
from typing import Annotated, get_args, get_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import BaseModel  # noqa: E402
from pydantic_core import PydanticUndefined  # noqa: E402

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
nitpick_ignore_regex = [
    (
        "py:class",
        r"(?:collections\.abc\.(?:Mapping|Sequence)|datetime(?:\.datetime)?|random\.Random|uuid\.UUID)",
    )
]
language = "ja"
html_search_language = "ja"
myst_enable_extensions = ["colon_fence"]

autodoc_typehints = "signature"
autodoc_member_order = "bysource"
autodoc_default_options = {"exclude-members": "model_config"}
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


def _pydantic_signature(app, what, name, obj, options, signature, return_annotation):
    """Pydantic modelのfield定義を通常のPython署名として返す。"""
    del app, name, options
    if what != "class" or not isinstance(obj, type) or not issubclass(obj, BaseModel):
        return signature, return_annotation
    parameters = []
    for parameter in inspect.signature(obj).parameters.values():
        field = obj.model_fields.get(parameter.name)
        if field is None:
            parameters.append(parameter)
            continue
        default = field.default
        if field.default_factory is not None:
            default = parameter.default
        elif field.is_required() or default is PydanticUndefined:
            default = inspect.Parameter.empty
        parameters.append(
            parameter.replace(
                annotation=_without_annotated_metadata(field.annotation),
                default=default,
            )
        )
    return str(inspect.Signature(parameters)), return_annotation


def _without_annotated_metadata(annotation):
    """Pydantic制約metadataを除いた利用者向け型注釈を返す。"""
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated:
        return _without_annotated_metadata(arguments[0])
    if origin is types.UnionType:
        return reduce(
            operator.or_,
            (_without_annotated_metadata(argument) for argument in arguments),
        )
    if origin is None:
        return annotation
    cleaned = tuple(_without_annotated_metadata(argument) for argument in arguments)
    try:
        return origin[cleaned]
    except TypeError:
        return annotation


def setup(app) -> None:
    """文書themeの日本語表示を登録する。"""
    app.connect("html-page-context", _localize_theme_labels)
    app.connect("autodoc-process-signature", _pydantic_signature)
