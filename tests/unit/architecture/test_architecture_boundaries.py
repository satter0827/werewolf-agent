"""Application architectureの実行可能な制約。"""

from __future__ import annotations

import ast
import importlib
import tomllib
from pathlib import Path

from scripts.architecture.analysis import (
    graph_cycles,
    imports_with_lines,
    module_name,
    project_import_edges,
)
from scripts.architecture.definition import (
    ALLOWED_IMPORTS,
    ALLOWED_MODULE_IMPORTS,
    CALL_RULES,
    CANONICAL_OPENAPI,
    ENTRYPOINTS,
    FORBIDDEN_PATHS,
    FRAMEWORK_RULES,
    LAYERS,
    PATH_RULES,
    ROOT_ENTRIES,
    SETTINGS_SECTIONS,
    THIN_MODULES,
)

import werewolf_agent.application as application
import werewolf_agent.domain as domain

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
IGNORED_ROOT_ENTRIES = {
    ".env",
    ".git",
    ".venv",
    ".werewolf-agent",
    "__pycache__",
}


def test_repository_layout_matches_the_architecture_manifest() -> None:
    """Repository rootとruntime境界をmanifestどおりに保つ。"""
    root_entries = {path.name for path in ROOT.iterdir() if path.name not in IGNORED_ROOT_ENTRIES}
    assert root_entries == ROOT_ENTRIES
    for layer in LAYERS:
        assert (PACKAGE / layer).is_dir(), layer
    assert (ROOT / CANONICAL_OPENAPI).is_file()
    assert (PACKAGE / "worker" / "app.py").is_file()
    assert (PACKAGE / "clients" / "cli" / "app.py").is_file()
    assert (PACKAGE / "clients" / "streamlit" / "app.py").is_file()
    for forbidden in FORBIDDEN_PATHS:
        assert not (ROOT / forbidden).exists(), forbidden
    for thin_module in THIN_MODULES:
        tree = ast.parse((ROOT / thin_module).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            for node in tree.body
        ), thin_module


def test_public_surfaces_are_minimal_and_explicit() -> None:
    """Pythonの公開面をdomainとapplicationに限定する。"""
    for module in (domain, application):
        assert module.__all__
        assert all(hasattr(module, name) for name in module.__all__)


def test_runtime_settings_are_owned_by_disjoint_manifest_sections() -> None:
    """Runtime設定fieldを変更理由ごとのsectionへ分離する。"""
    section_fields: dict[str, set[str]] = {}
    for name, target in SETTINGS_SECTIONS.items():
        module_name_value, class_name = target.split(":", maxsplit=1)
        section = getattr(importlib.import_module(module_name_value), class_name)
        section_fields[name] = set(section.model_fields)

    owners: dict[str, list[str]] = {}
    for section_name, fields in section_fields.items():
        for field in fields:
            owners.setdefault(field, []).append(section_name)

    from werewolf_agent.settings import AppSettings

    assert set(AppSettings.model_fields) == set(owners)
    assert all(len(field_owners) == 1 for field_owners in owners.values())

    tree = ast.parse((PACKAGE / "settings" / "settings.py").read_text(encoding="utf-8"))
    app_settings = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AppSettings"
    )
    assert not any(isinstance(node, ast.AnnAssign) for node in app_settings.body)


def test_log_event_names_are_owned_by_the_recording_boundary() -> None:
    """横断的なsettings文言集へprocess固有eventを戻さない。"""
    tree = ast.parse((PACKAGE / "settings" / "messages.py").read_text(encoding="utf-8"))
    assigned_names = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    assert not {name for name in assigned_names if name.startswith("LOG_")}


def test_layer_imports_follow_the_allowed_matrix() -> None:
    """Layer間importをmanifestの許可方向に限定する。"""
    offenders = [
        (edge.path, edge.source_layer, edge.target_layer)
        for edge in project_import_edges()
        if edge.target_layer not in ALLOWED_IMPORTS[edge.source_layer]
        and (edge.source_module, edge.target_layer) not in ALLOWED_MODULE_IMPORTS
    ]
    assert not offenders


def test_layer_and_module_graphs_have_no_cycles() -> None:
    """Layerとmoduleの循環依存を禁止する。"""
    layer_graph: dict[str, set[str]] = {layer: set() for layer in LAYERS}
    for edge in project_import_edges():
        if edge.source_layer != edge.target_layer:
            layer_graph[edge.source_layer].add(edge.target_layer)
    assert not graph_cycles(layer_graph)

    modules = {module_name(path): path for path in PACKAGE.rglob("*.py")}
    module_graph = {
        module: {
            imported for imported in _imports(path) if imported in modules and imported != module
        }
        for module, path in modules.items()
    }
    assert not graph_cycles(module_graph)


def test_frameworks_stay_in_manifest_owned_roots() -> None:
    """外部frameworkをmanifestで宣言したadapterまたはprocessに隔離する。"""
    offenders: list[tuple[Path, str, str]] = []
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(ROOT)
        for imported in _imports(path):
            for name, rule in FRAMEWORK_RULES.items():
                if any(
                    imported == prefix or imported.startswith(f"{prefix}.")
                    for prefix in rule.imports
                ) and not any(relative.is_relative_to(root) for root in rule.roots):
                    offenders.append((relative, imported, name))
    assert not offenders


def test_api_routes_only_use_application_contracts() -> None:
    """Path単位のimport制約をmanifestから評価する。"""
    offenders = [
        (name, path.relative_to(ROOT), imported)
        for name, rule in PATH_RULES.items()
        for source_root in rule.roots
        for path in (ROOT / source_root).rglob("*.py")
        for imported in _imports(path)
        if imported.startswith(rule.forbidden)
    ]
    assert not offenders


def test_processes_do_not_execute_adapter_owned_operations() -> None:
    """Processからdatabase methodを直接呼ばない。"""
    offenders: list[tuple[str, Path, str]] = []
    for name, rule in CALL_RULES.items():
        for source_root in rule.roots:
            for path in (ROOT / source_root).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in rule.forbidden
                    ):
                        offenders.append((name, path.relative_to(ROOT), node.func.attr))
    assert not offenders


def test_clients_use_the_http_game_client_factory() -> None:
    """Client用factoryをSupabase実装から分離する。"""
    factory_imports = _imports(PACKAGE / "adapters" / "factory.py")
    assert "werewolf_agent.adapters.http" in factory_imports
    assert not any(name.startswith("werewolf_agent.adapters.supabase") for name in factory_imports)


def test_console_entrypoints_match_the_architecture_manifest() -> None:
    """配布するconsole commandの実装先をmanifestと一致させる。"""
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    assert project["scripts"] == {
        "werewolf-agent": ENTRYPOINTS["cli"],
        "werewolf-agent-api": ENTRYPOINTS["api"],
        "werewolf-agent-worker": ENTRYPOINTS["worker"],
    }


def test_domain_and_application_have_no_io_or_logging_dependencies() -> None:
    """Domainとapplicationを外部I/Oおよびloggingから分離する。"""
    forbidden = (
        "httpx",
        "langchain",
        "langgraph",
        "logging",
        "os",
        "pathlib",
        "psycopg",
        "sqlalchemy",
        "structlog",
        "tomllib",
    )
    offenders = [
        (path.relative_to(ROOT), imported)
        for root in (PACKAGE / "domain", PACKAGE / "application")
        for path in root.rglob("*.py")
        for imported in _imports(path)
        if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden)
    ]
    assert not offenders


def _imports(path: Path) -> set[str]:
    return {imported for imported, _ in imports_with_lines(path, module_name(path))}
