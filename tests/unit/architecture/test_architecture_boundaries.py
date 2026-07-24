"""Executable architecture constraints for the headless core."""

from __future__ import annotations

import ast
from pathlib import Path

import werewolf_agent.adapters as adapters
import werewolf_agent.agents as agents
import werewolf_agent.domain as domain
import werewolf_agent.usecase as usecase

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
UNIT_TESTS = ROOT / "tests" / "unit"

LAYERS = {
    "domain",
    "configuration",
    "contracts",
    "security",
    "observability",
    "agents",
    "usecase",
    "adapters",
    "interfaces",
    "resources",
}
ALLOWED_IMPORTS = {
    "domain": {"domain"},
    "configuration": {"configuration"},
    "contracts": {"contracts", "configuration", "security"},
    "security": {"security", "configuration"},
    "observability": {"observability", "configuration", "contracts", "security"},
    "agents": {"agents", "configuration", "contracts"},
    "usecase": {"usecase", "domain", "configuration", "contracts"},
    "adapters": {
        "adapters",
        "agents",
        "configuration",
        "contracts",
        "domain",
        "observability",
        "security",
        "usecase",
    },
    "interfaces": {
        "interfaces",
        "adapters",
        "configuration",
        "contracts",
        "observability",
        "security",
    },
    "resources": {"resources"},
}


def test_top_level_layout_uses_intuitive_boundaries() -> None:
    assert not (ROOT / "backend").exists()
    assert (ROOT / "src" / "werewolf_agent").is_dir()

    for layer in LAYERS:
        assert (PACKAGE / layer).exists(), layer

    for removed in ("api", "entrypoint", "interface", "commons"):
        assert not list((PACKAGE / removed).rglob("*.py")), removed

    assert not list((PACKAGE / "domain" / "game").rglob("*.py"))
    assert not list((PACKAGE / "domain" / "llm").rglob("*.py"))
    assert not list((PACKAGE / "usecase" / "jobs").rglob("*.py"))
    assert not list((PACKAGE / "usecase" / "internal").rglob("*.py"))

    assert {
        path.name for path in UNIT_TESTS.iterdir() if path.is_dir() and path.name != "__pycache__"
    } == {
        "adapters",
        "agents",
        "architecture",
        "configuration",
        "contracts",
        "domain",
        "interfaces",
        "observability",
        "security",
        "usecase",
    }


def test_public_surfaces_are_explicit() -> None:
    assert set(domain.__all__) == {
        "Action",
        "Game",
        "GameEvent",
        "GameSetup",
        "GameState",
        "GameView",
        "RuleRegistry",
        "RuleSet",
        "RuleSetDefinition",
        "RuleViolation",
    }
    assert set(adapters.__all__) == {"GameClient", "build_game_client"}
    assert set(agents.__all__) == {
        "AgentActionType",
        "AgentDecision",
        "AgentObservation",
        "AgentPhase",
        "AgentPlayerStatus",
        "AgentScenario",
        "PlayerAgent",
        "PlayerProfile",
        "PlayerProfileCatalog",
        "VisiblePlayer",
    }
    assert set(usecase.__all__) == {
        "AdvanceGameCommand",
        "AdvanceGameResult",
        "CreateGameCommand",
        "GameListResult",
        "GameResult",
        "GameRevealResult",
        "GameTimelineResult",
        "GetGameQuery",
        "GetGameRevealQuery",
        "GetPlayerObservationQuery",
        "ListGamesQuery",
        "ListTimelineQuery",
        "PlayerActionCommand",
        "PlayerActionResult",
        "PlayerObservationResult",
        "UsecaseContext",
        "advance_game",
        "create_game",
        "get_game",
        "get_game_reveal",
        "get_player_observation",
        "list_games",
        "list_timeline",
        "submit_player_action",
    }


def test_layer_imports_follow_the_allowed_matrix() -> None:
    offenders: list[tuple[Path, str, str]] = []
    for path, module in _project_imports():
        source_layer = path.relative_to(PACKAGE).parts[0]
        if source_layer not in LAYERS:
            continue
        target_parts = module.split(".")
        if len(target_parts) < 2 or target_parts[0] != "werewolf_agent":
            continue
        target_layer = target_parts[1]
        if target_layer in LAYERS and target_layer not in ALLOWED_IMPORTS[source_layer]:
            offenders.append((path.relative_to(ROOT), source_layer, target_layer))
    assert not offenders


def test_project_layer_graph_has_no_cycles() -> None:
    graph: dict[str, set[str]] = {layer: set() for layer in LAYERS}
    for path, module in _project_imports():
        source = path.relative_to(PACKAGE).parts[0]
        if source not in LAYERS:
            continue
        parts = module.split(".")
        if len(parts) >= 2 and parts[0] == "werewolf_agent" and parts[1] in LAYERS:
            target = parts[1]
            if target != source:
                graph[source].add(target)
    assert not _cycles(graph)


def test_project_module_graph_has_no_cycles() -> None:
    modules = {_module_name(path): path for path in PACKAGE.rglob("*.py")}
    graph: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        for imported in _imports(path):
            if imported in modules and imported != module:
                graph[module].add(imported)
    assert not _cycles(graph)


def test_frameworks_stay_at_their_adapters() -> None:
    rules = {
        ("langchain", "langgraph"): PACKAGE / "agents" / "langchain",
        ("psycopg", "sqlalchemy"): PACKAGE / "adapters" / "supabase",
        ("streamlit",): PACKAGE / "interfaces" / "streamlit",
        ("typer",): PACKAGE / "interfaces",
    }
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        for imported in _imports(path):
            for prefixes, allowed_root in rules.items():
                if any(
                    imported == prefix or imported.startswith(f"{prefix}.") for prefix in prefixes
                ) and not path.is_relative_to(allowed_root):
                    offenders.append((path.relative_to(ROOT), imported))
    assert not offenders


def test_outer_layers_use_only_the_domain_public_module() -> None:
    offenders = []
    for layer in ("usecase", "agents", "adapters", "interfaces"):
        for path in (PACKAGE / layer).rglob("*.py"):
            for imported in _imports(path):
                if imported.startswith("werewolf_agent.domain."):
                    offenders.append((path.relative_to(ROOT), imported))
    assert not offenders


def test_game_module_exposes_only_the_aggregate_root() -> None:
    path = PACKAGE / "domain" / "game.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    public_definitions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_definitions == {"Game"}


def test_usecase_changes_game_state_only_through_aggregate() -> None:
    handlers = (PACKAGE / "usecase" / "handlers.py").read_text(encoding="utf-8")
    for legacy_function in ("start_game", "submit_action", "advance_phase", "observe"):
        assert f"{legacy_function}(" not in handlers


def test_usecase_does_not_own_agent_runtime_or_telemetry() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (PACKAGE / "usecase").rglob("*.py")
    )
    for removed_runtime_type in (
        "LlmProviderConfig",
        "LlmTraceSink",
        "TelemetryEvent",
        "TelemetrySink",
    ):
        assert removed_runtime_type not in source


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


def test_game_identifiers_do_not_leak_into_outer_business_logic() -> None:
    fixed_ids = {
        "villager",
        "werewolf",
        "seer",
        "knight",
        "village",
        "night_attack",
        "pack_knowledge",
        "inspect",
        "guard",
    }
    offenders = []
    for layer in ("usecase", "adapters", "interfaces"):
        for path in (PACKAGE / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and node.value in fixed_ids:
                    offenders.append((path.relative_to(ROOT), node.lineno, node.value))
    assert not offenders


def test_langchain_fake_is_the_library_implementation() -> None:
    service = (PACKAGE / "agents" / "langchain" / "service.py").read_text(encoding="utf-8")
    assert "from langchain_core.language_models.fake import FakeListLLM" in service
    assert "class Fake" not in service
    assert "_fake_response_selector" not in service
    assert "_fake_template_context" not in service


def _project_imports() -> list[tuple[Path, str]]:
    return [
        (path, imported)
        for path in PACKAGE.rglob("*.py")
        for imported in _imports(path)
        if imported == "werewolf_agent" or imported.startswith("werewolf_agent.")
    ]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()

    class ImportVisitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                for child in node.orelse:
                    self.visit(child)
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            imports.update(alias.name for alias in node.names)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module:
                imports.add(node.module)

    ImportVisitor().visit(tree)
    return imports


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("werewolf_agent", *parts))


def _cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: tuple[str, ...]) -> None:
        if node in path:
            cycle = path[path.index(node) :]
            rotations = [cycle[index:] + cycle[:index] for index in range(len(cycle))]
            found.add(min(rotations))
            return
        for target in graph.get(node, set()):
            visit(target, (*path, node))

    for node in graph:
        visit(node, ())
    return sorted(found)
