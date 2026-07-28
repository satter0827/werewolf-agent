"""Architecture解析と文書生成が共有する構造定義。"""

from __future__ import annotations

import importlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

RULES_PATH = Path(__file__).with_name("rules.toml")


@dataclass(frozen=True, slots=True)
class FrameworkRule:
    """外部frameworkを使用できるsource root。"""

    imports: tuple[str, ...]
    roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PathRule:
    """特定source rootで禁止するproject import。"""

    roots: tuple[str, ...]
    forbidden: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CallRule:
    """特定source rootで禁止するmethod call。"""

    roots: tuple[str, ...]
    forbidden: tuple[str, ...]


def _load_rules() -> dict[str, Any]:
    with RULES_PATH.open("rb") as stream:
        return tomllib.load(stream)


_RULES = _load_rules()
_LAYER_RULES = _RULES["layers"]
_EXCEPTION_RULES = _RULES.get("dependency_exceptions", {})
_FRAMEWORK_RULES = _RULES.get("frameworks", {})
_PATH_RULES = _RULES.get("path_rules", {})
_CALL_RULES = _RULES.get("call_rules", {})

assert isinstance(_LAYER_RULES, dict)
assert isinstance(_EXCEPTION_RULES, dict)
assert isinstance(_FRAMEWORK_RULES, dict)
assert isinstance(_PATH_RULES, dict)
assert isinstance(_CALL_RULES, dict)

LAYERS = frozenset(_LAYER_RULES)
ALLOWED_IMPORTS = {
    layer: frozenset(rule["allowed"])
    for layer, rule in _LAYER_RULES.items()
    if isinstance(rule, dict)
}
DEPENDENCY_EXCEPTION_REASONS = {
    tuple(key.split("|", maxsplit=1)): value["reason"]
    for key, value in _EXCEPTION_RULES.items()
    if isinstance(value, dict)
}
ALLOWED_MODULE_IMPORTS = frozenset(DEPENDENCY_EXCEPTION_REASONS)
PUBLIC_MODULE_NAMES = tuple(str(name) for name in _RULES["public_modules"])
PUBLIC_MODULES: tuple[ModuleType, ...] = tuple(
    importlib.import_module(name) for name in PUBLIC_MODULE_NAMES
)
ROOT_ENTRIES = frozenset(str(name) for name in _RULES["root_entries"])
THIN_MODULES = tuple(str(path) for path in _RULES["thin_modules"])
CANONICAL_OPENAPI = str(_RULES["canonical_openapi"])
ENTRYPOINTS = {str(name): str(value) for name, value in _RULES["entrypoints"].items()}
FRAMEWORK_RULES = {
    name: FrameworkRule(
        imports=tuple(str(value) for value in rule["imports"]),
        roots=tuple(str(value) for value in rule["roots"]),
    )
    for name, rule in _FRAMEWORK_RULES.items()
    if isinstance(rule, dict)
}
FORBIDDEN_PATHS = tuple(str(path) for path in _RULES["forbidden_paths"])
PATH_RULES = {
    name: PathRule(
        roots=tuple(str(value) for value in rule["roots"]),
        forbidden=tuple(str(value) for value in rule["forbidden"]),
    )
    for name, rule in _PATH_RULES.items()
    if isinstance(rule, dict)
}
CALL_RULES = {
    name: CallRule(
        roots=tuple(str(value) for value in rule["roots"]),
        forbidden=tuple(str(value) for value in rule["forbidden"]),
    )
    for name, rule in _CALL_RULES.items()
    if isinstance(rule, dict)
}
SETTINGS_SECTIONS = {str(name): str(value) for name, value in _RULES["settings_sections"].items()}

__all__ = [
    "ALLOWED_IMPORTS",
    "ALLOWED_MODULE_IMPORTS",
    "CALL_RULES",
    "CANONICAL_OPENAPI",
    "DEPENDENCY_EXCEPTION_REASONS",
    "ENTRYPOINTS",
    "FORBIDDEN_PATHS",
    "FRAMEWORK_RULES",
    "LAYERS",
    "PATH_RULES",
    "PUBLIC_MODULES",
    "PUBLIC_MODULE_NAMES",
    "ROOT_ENTRIES",
    "RULES_PATH",
    "SETTINGS_SECTIONS",
    "THIN_MODULES",
    "CallRule",
    "FrameworkRule",
    "PathRule",
]
