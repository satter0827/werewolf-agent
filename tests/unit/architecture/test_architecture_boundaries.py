"""Executable architecture constraints for the application."""

from __future__ import annotations

from pathlib import Path

from scripts.architecture.analysis import (
    graph_cycles,
    imports_with_lines,
    module_name,
    project_import_edges,
)
from scripts.architecture.definition import ALLOWED_IMPORTS, ALLOWED_MODULE_IMPORTS, LAYERS

import werewolf_agent.adapters as adapters
import werewolf_agent.agents as agents
import werewolf_agent.domain as domain
import werewolf_agent.usecase as usecase

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"


def test_top_level_layout_has_independent_runtime_boundaries() -> None:
    for layer in LAYERS:
        assert (PACKAGE / layer).is_dir(), layer
    assert (ROOT / "frontend").is_dir()
    assert (ROOT / "frontend" / "e2e" / "react.spec.ts").is_file()
    assert (ROOT / "frontend" / "e2e" / "streamlit.spec.ts").is_file()
    assert (ROOT / "scripts" / "supabase" / "migrations.py").is_file()
    assert (ROOT / "scripts" / "contracts" / "openapi.py").is_file()
    assert not (ROOT / "e2e").exists()
    assert not (ROOT / "tools").exists()
    assert not (PACKAGE / "interfaces" / "api").exists()
    assert (PACKAGE / "interfaces" / "worker" / "app.py").is_file()
    assert (PACKAGE / "interfaces" / "worker" / "service.py").is_file()
    assert not list((PACKAGE / "worker").rglob("*.py"))
    assert not list((PACKAGE / "adapters" / "supabase" / "worker").rglob("*.py"))
    assert not (PACKAGE / "adapters" / "supabase" / "game_client.py").exists()


def test_public_surfaces_are_minimal_and_explicit() -> None:
    for module in (domain, adapters, agents, usecase):
        assert module.__all__
        assert all(hasattr(module, name) for name in module.__all__)


def test_layer_imports_follow_the_allowed_matrix() -> None:
    offenders = [
        (edge.path, edge.source_layer, edge.target_layer)
        for edge in project_import_edges()
        if edge.target_layer not in ALLOWED_IMPORTS[edge.source_layer]
        and (edge.source_module, edge.target_layer) not in ALLOWED_MODULE_IMPORTS
    ]
    assert not offenders


def test_layer_and_module_graphs_have_no_cycles() -> None:
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


def test_frameworks_stay_in_their_runtime_adapters() -> None:
    rules = {
        ("fastapi", "starlette", "uvicorn"): (PACKAGE / "api",),
        ("langchain", "langgraph"): (PACKAGE / "agents" / "langchain",),
        ("psycopg", "sqlalchemy"): (PACKAGE / "adapters" / "supabase",),
        ("streamlit",): (PACKAGE / "interfaces" / "streamlit",),
        ("typer",): (
            PACKAGE / "interfaces" / "cli",
            PACKAGE / "interfaces" / "worker",
        ),
    }
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        for imported in _imports(path):
            for prefixes, roots in rules.items():
                if any(
                    imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes
                ) and not any(path.is_relative_to(root) for root in roots):
                    offenders.append((path.relative_to(ROOT), imported))
    assert not offenders


def test_api_routes_only_use_application_contracts() -> None:
    offenders = []
    for path in (PACKAGE / "api" / "routes").rglob("*.py"):
        for imported in _imports(path):
            if imported.startswith(
                (
                    "werewolf_agent.domain",
                    "werewolf_agent.agents",
                    "werewolf_agent.adapters",
                    "werewolf_agent.usecase.handlers",
                    "werewolf_agent.usecase.models",
                    "werewolf_agent.usecase.ports",
                )
            ):
                offenders.append((path.relative_to(ROOT), imported))
    assert not offenders


def test_interfaces_can_only_reach_games_through_http_client_port() -> None:
    offenders = []
    for interface in ("cli", "streamlit"):
        for path in (PACKAGE / "interfaces" / interface).rglob("*.py"):
            for imported in _imports(path):
                if imported.startswith(
                    (
                        "werewolf_agent.domain",
                        "werewolf_agent.usecase",
                        "werewolf_agent.adapters.supabase",
                    )
                ):
                    offenders.append((path.relative_to(ROOT), imported))
    assert not offenders
    factory_imports = _imports(PACKAGE / "adapters" / "factory.py")
    assert "werewolf_agent.adapters.http" in factory_imports
    assert not any(name.startswith("werewolf_agent.adapters.supabase") for name in factory_imports)


def test_domain_and_usecase_have_no_io_or_logging_dependencies() -> None:
    forbidden = (
        "logging",
        "structlog",
        "os",
        "pathlib",
        "tomllib",
        "httpx",
        "psycopg",
        "sqlalchemy",
        "langchain",
        "langgraph",
    )
    offenders = []
    for root in (PACKAGE / "domain", PACKAGE / "usecase"):
        for path in root.rglob("*.py"):
            for imported in _imports(path):
                if any(
                    imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden
                ):
                    offenders.append((path.relative_to(ROOT), imported))
    assert not offenders


def _imports(path: Path) -> set[str]:
    return {imported for imported, _ in imports_with_lines(path, module_name(path))}
