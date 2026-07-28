"""Application architectureの実行可能な制約。"""

from __future__ import annotations

import ast
import importlib
import sys
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
    assert set(domain.__all__) == {
        "AbilityDefinition",
        "Action",
        "ActionType",
        "AvailableAction",
        "EventVisibility",
        "Game",
        "GameConfig",
        "GameEvent",
        "GameSetup",
        "GameState",
        "GameView",
        "LocalRules",
        "Phase",
        "Player",
        "PlayerStatus",
        "RoleCatalog",
        "RoleDefinition",
        "RuleSet",
        "RuleSetDefinition",
        "RuleViolation",
        "WinResult",
        "build_game_rules",
    }
    assert set(application.__all__) == {
        "AccessPolicy",
        "Actor",
        "AdvanceGameResult",
        "ApplicationContext",
        "CreateGameCommand",
        "ComputedAdvanceGame",
        "GameApplication",
        "GameApplicationConfig",
        "GameListResult",
        "GameRepository",
        "GameResult",
        "GameRevealResult",
        "GameTimelineResult",
        "GameSetupDocument",
        "LocalRulesDefinition",
        "OperationQueue",
        "PlayerActionCommand",
        "PlayerActionResult",
        "PlayerObservationResult",
        "PreparedAdvanceGame",
        "ReplayVerificationResult",
        "SetupValidationResult",
        "SetupApplication",
        "SetupRepository",
        "validate_setup_document",
    }


def test_create_restore_and_replay_share_the_domain_rule_factory() -> None:
    owners = (
        PACKAGE / "application" / "handlers" / "games.py",
        PACKAGE / "application" / "handlers" / "common.py",
        PACKAGE / "application" / "replay.py",
    )

    for owner in owners:
        source = owner.read_text(encoding="utf-8")
        assert "build_game_rules(" in source, owner
        assert "RuleRegistry" not in source, owner


def test_replay_verifies_every_create_command_checksum() -> None:
    worker_store = (PACKAGE / "adapters" / "supabase" / "worker_store.py").read_text(
        encoding="utf-8"
    )
    replay = (PACKAGE / "application" / "replay.py").read_text(encoding="utf-8")

    for checksum in ("setup_checksum", "mechanics_checksum", "roster_checksum"):
        assert f'"{checksum}": stored_config.get("{checksum}")' in worker_store
        assert f'genesis["{checksum}"]' in replay


def test_domain_uses_only_the_standard_library_and_domain_modules() -> None:
    """Domainへvalidation frameworkや他layerを持ち込まない。"""
    offenders = [
        (path.relative_to(ROOT), imported)
        for path in (PACKAGE / "domain").rglob("*.py")
        for imported in _imports(path)
        if imported.split(".", maxsplit=1)[0] not in sys.stdlib_module_names
        and not imported.startswith("werewolf_agent.domain")
    ]
    assert not offenders


def test_api_routes_do_not_invoke_access_or_queue_adapters_directly() -> None:
    """認可とcommand受付をapplication facadeへ集約する。"""
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (PACKAGE / "api" / "routes").glob("*.py")
    )
    assert "services.access" not in source
    assert "services.operations" not in source


def test_worker_invokes_application_through_the_public_facade() -> None:
    """Workerからapplication handlerの直接実行を禁止する。"""
    worker = PACKAGE / "worker" / "service.py"
    imports = _imports(worker)
    assert "werewolf_agent.application.handlers" not in imports
    assert "build_setup_catalog" not in worker.read_text(encoding="utf-8")


def test_persisted_game_versions_are_append_only() -> None:
    """保存済みversionをrepositoryのupsertで書き換えない。"""
    source = (PACKAGE / "adapters" / "supabase" / "repository.py").read_text(encoding="utf-8")
    insert_state_version = source.split("def _insert_state_version", maxsplit=1)[1].split(
        "def _append_state_event", maxsplit=1
    )[0]
    assert "on conflict" not in insert_state_version.lower()


def test_legacy_domain_aliases_and_plural_faction_ids_do_not_return() -> None:
    """同義domain型とclient固有のfaction IDを再導入しない。"""
    domain_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (PACKAGE / "domain").rglob("*.py")
    )
    for alias in ("GameSnapshot =", "Observation =", "DomainEvent ="):
        assert alias not in domain_source

    runtime_roots = (PACKAGE, ROOT / "scripts")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in runtime_roots
        for pattern in ("*.py",)
        for path in root.rglob(pattern)
    )
    assert '"villagers"' not in source
    assert '"werewolves"' not in source
    assert "'villagers'" not in source
    assert "'werewolves'" not in source

    assert "CreateGameRequest" not in application.__all__
    assert "PlayerActionRequest" not in application.__all__


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


def test_agent_contract_layer_contains_no_langchain_specific_surface() -> None:
    """Provider非依存のagents層へLangChain固有名を公開しない。"""
    offenders = [
        path.relative_to(ROOT)
        for path in (PACKAGE / "agents").rglob("*.py")
        if "langchain" in path.read_text(encoding="utf-8").lower()
        or "langgraph" in path.read_text(encoding="utf-8").lower()
    ]
    assert not offenders


def test_packaged_toml_owns_non_secret_runtime_defaults() -> None:
    """Settings sectionへTOMLと重複するdefault値を戻さない。"""
    offenders: list[tuple[Path, int]] = []
    for path in (PACKAGE / "settings" / "sections").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            if node.target.id == "openai_api_key" or not isinstance(node.value, ast.Call):
                continue
            if any(keyword.arg == "default" for keyword in node.value.keywords):
                offenders.append((path.relative_to(ROOT), node.lineno))
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


def test_environment_access_stays_at_configuration_and_process_boundaries() -> None:
    """環境変数の読込みをsettingsとentrypointへ限定する。"""
    allowed = {
        PACKAGE / "api" / "app.py",
        PACKAGE / "clients" / "cli" / "app.py",
        PACKAGE / "clients" / "streamlit" / "app.py",
        PACKAGE / "settings" / "settings.py",
        PACKAGE / "worker" / "app.py",
    }
    offenders: list[tuple[Path, int]] = []
    for path in PACKAGE.rglob("*.py"):
        if path in allowed or path.is_relative_to(PACKAGE / "settings"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr in {"environ", "getenv"}
            ) or (
                isinstance(node, ast.ImportFrom)
                and node.module == "os"
                and any(name.name in {"environ", "getenv"} for name in node.names)
            ):
                offenders.append((path.relative_to(ROOT), node.lineno))
    assert not offenders


def _imports(path: Path) -> set[str]:
    return {imported for imported, _ in imports_with_lines(path, module_name(path))}
