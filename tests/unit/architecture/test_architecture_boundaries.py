import ast
import inspect
from pathlib import Path
from types import ModuleType

import werewolf_agent.domain.llm as llm_domain
import werewolf_agent.usecase.jobs as game_jobs

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "backend" / "src" / "werewolf_agent"


def test_interface_entrypoints_do_not_import_domain_or_usecase_directly() -> None:
    forbidden_prefixes = (
        "werewolf_agent.domain",
        "werewolf_agent.usecase",
        "werewolf_agent.llm",
    )

    entrypoint_path = PACKAGE / "interface" / "entrypoint"
    imported = _imports_under(entrypoint_path / "api")
    imported.extend(_imports_under(entrypoint_path / "cui"))
    imported.extend(_imports_under(entrypoint_path / "streamlit"))

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_interface_imports_only_public_usecase_jobs_from_application_bridge() -> None:
    imported = _imports_under(PACKAGE / "interface")
    application_path = PACKAGE / "interface" / "application"
    allowed_module = "werewolf_agent.usecase.jobs"

    assert not [
        (path, module)
        for path, module in imported
        if (module == "werewolf_agent.usecase" or module.startswith("werewolf_agent.usecase."))
        and (not path.is_relative_to(application_path) or module != allowed_module)
    ]


def test_api_routes_leave_game_id_parsing_to_usecase() -> None:
    router_source = (PACKAGE / "interface" / "api" / "routers.py").read_text(encoding="utf-8")

    assert "game_id: UUID" not in router_source
    assert "game_id: str" in router_source


def test_usecase_jobs_public_surface_is_minimal() -> None:
    _assert_public_surface(
        game_jobs,
        {
            "AdvanceGameRunCommand",
            "AdvanceGameRunResult",
            "ActionTypeId",
            "CreateGameRunCommand",
            "GameEventCreate",
            "GamePhase",
            "GameRepository",
            "GameRunCreate",
            "GameRunResult",
            "GameRunUpdate",
            "GameStatus",
            "GameUseCaseConfig",
            "GameUseCaseDependencies",
            "GetGameRunQuery",
            "GetPlayerObservationQuery",
            "ListGameRunsQuery",
            "ListGameRunsResult",
            "ListPublicGameEventsQuery",
            "ListPublicGameTurnsQuery",
            "ListPublicGameTurnsResult",
            "LlmProviderConfig",
            "PlayerObservationResult",
            "PublicGameEventsResult",
            "PublicGameRunSummary",
            "PublicGameTurn",
            "RulesetResult",
            "StoredGameEvent",
            "StoredGameRun",
            "StoredGameRunSummary",
            "StoredGameTurn",
            "SubmitPlayerActionCommand",
            "SubmitPlayerActionResult",
            "advance_game_run",
            "create_game_run",
            "get_default_ruleset",
            "get_player_observation",
            "get_game_run",
            "list_game_runs",
            "list_public_game_events",
            "list_public_game_turns",
            "submit_player_action",
        },
    )


def test_old_usecase_jobs_names_are_not_public() -> None:
    removed_names = {
        "AdvanceGameCommand",
        "AdvanceGameResult",
        "CreateGameCommand",
        "GameResult",
        "GameRunsResult",
        "GameTurnsResult",
        "GetGameQuery",
        "GetPrivateObservationQuery",
        "ListGameTurnsQuery",
        "ListGamesQuery",
        "ListPublicEventsQuery",
        "PrivateObservationResult",
        "PublicEventsResult",
        "advance_game",
        "create_game",
        "get_game",
        "get_private_observation",
        "list_game_turns",
        "list_games",
        "list_public_events",
    }

    assert not [name for name in removed_names if hasattr(game_jobs, name)]


def test_domain_llm_public_surface_is_minimal() -> None:
    _assert_public_surface(
        llm_domain,
        {
            "AgentActionType",
            "AgentDecision",
            "AgentObservation",
            "AgentPhase",
            "AgentPlayerStatus",
            "AgentRole",
            "FakeResponseResource",
            "LangChainDecisionProvider",
            "LlmDecisionProvider",
            "PromptMessage",
            "PromptResource",
            "VisiblePlayer",
            "build_fake_decision_provider",
            "load_fake_response_resource",
            "load_prompt_resource",
        },
    )


def test_usecase_jobs_are_stateless_command_or_query_functions() -> None:
    for function_name in (
        "create_game_run",
        "get_game_run",
        "get_player_observation",
        "submit_player_action",
        "advance_game_run",
        "list_game_runs",
        "list_public_game_events",
        "list_public_game_turns",
    ):
        signature = inspect.signature(getattr(game_jobs, function_name))
        parameters = list(signature.parameters.values())

        assert len(parameters) == 2
        assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert parameters[1].name == "dependencies"
        assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY

    ruleset_signature = inspect.signature(game_jobs.get_default_ruleset)
    assert list(ruleset_signature.parameters) == ["config"]
    assert ruleset_signature.parameters["config"].kind is inspect.Parameter.KEYWORD_ONLY


def test_usecase_imports_domain_only_from_internal_boundary() -> None:
    allowed_domain_modules = {
        "werewolf_agent.domain.game.models",
        "werewolf_agent.domain.game.service",
        "werewolf_agent.domain.llm.models",
        "werewolf_agent.domain.llm.ports",
        "werewolf_agent.domain.llm.service",
    }

    imported = _imports_under(PACKAGE / "usecase")
    internal_path = PACKAGE / "usecase" / "internal"
    bad_imports = []
    for path, module in imported:
        if not module.startswith("werewolf_agent.domain"):
            continue
        if not path.is_relative_to(internal_path) or module not in allowed_domain_modules:
            bad_imports.append((path, module))

    assert not bad_imports


def test_usecase_internal_does_not_import_interface_or_wire_contracts() -> None:
    forbidden_prefixes = (
        "werewolf_agent.interface",
        "werewolf_agent.contracts.schemas",
        "fastapi",
        "starlette",
        "sse_starlette",
    )

    imported = _imports_under(PACKAGE / "usecase" / "internal")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_interface_application_bridge_is_stateless() -> None:
    app_source = (PACKAGE / "interface" / "api" / "app.py").read_text(encoding="utf-8")
    bridge_source = (PACKAGE / "interface" / "application" / "games.py").read_text(encoding="utf-8")

    assert "class GameApplication" not in bridge_source
    assert "app.state.game_application" not in app_source


def test_game_and_llm_subdomains_do_not_import_each_other() -> None:
    imported_by_game = _imports_under(PACKAGE / "domain" / "game")
    imported_by_llm = _imports_under(PACKAGE / "domain" / "llm")

    assert not [
        (path, module)
        for path, module in imported_by_game
        if module == "werewolf_agent.domain.llm" or module.startswith("werewolf_agent.domain.llm.")
    ]
    assert not [
        (path, module)
        for path, module in imported_by_llm
        if module == "werewolf_agent.domain.game"
        or module.startswith("werewolf_agent.domain.game.")
    ]


def test_commons_do_not_import_usecase_or_interfaces() -> None:
    forbidden_prefixes = (
        "werewolf_agent.usecase",
        "werewolf_agent.interface",
    )

    imported = _imports_under(PACKAGE / "commons")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_external_wire_schemas_are_imported_from_contracts() -> None:
    imported = _imports_under(PACKAGE / "interface")

    assert not [
        (path, module)
        for path, module in imported
        if module == "werewolf_agent.interface.shared.schemas"
        or module.startswith("werewolf_agent.interface.shared.schemas.")
    ]


def test_interface_shared_does_not_import_entrypoint_ui_libraries() -> None:
    forbidden_modules = (
        "rich",
        "streamlit",
        "typer",
        "werewolf_agent.interface.entrypoint",
    )

    imported = _imports_under(PACKAGE / "interface" / "shared")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_streamlit_view_models_do_not_import_ui_or_inner_layers() -> None:
    forbidden_modules = (
        "rich",
        "streamlit",
        "typer",
        "werewolf_agent.domain",
        "werewolf_agent.interface.shared",
        "werewolf_agent.usecase",
    )

    imported = _imports_under(PACKAGE / "interface" / "entrypoint" / "streamlit")
    view_model_imports = [
        (path, module) for path, module in imported if path.name == "view_models.py"
    ]

    assert not [
        (path, module)
        for path, module in view_model_imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_contracts_do_not_import_api_frameworks() -> None:
    forbidden_modules = (
        "fastapi",
        "starlette",
        "sse_starlette",
    )

    imported = _imports_under(PACKAGE / "contracts")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_domain_does_not_import_outer_layers() -> None:
    allowed_commons_modules = {
        "werewolf_agent.commons.shared.messages",
        "werewolf_agent.commons.shared.validation",
    }
    forbidden_prefixes = (
        "werewolf_agent.usecase",
        "werewolf_agent.interface",
        "werewolf_agent.commons",
        "werewolf_agent.llm",
    )

    imported = _imports_under(PACKAGE / "domain")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
        and module not in allowed_commons_modules
    ]


def test_removed_import_paths_do_not_exist() -> None:
    assert not (PACKAGE / "interface" / "entrypoint" / "api").exists()
    assert not (PACKAGE / "interface" / "entrypoint" / "cli").exists()
    assert not (PACKAGE / "interface" / "cui").exists()
    assert not (PACKAGE / "interface" / "streamlit").exists()
    assert not list((PACKAGE / "configuration").glob("*.py"))
    assert not (PACKAGE / "configuration" / "defaults.toml").exists()
    assert not (PACKAGE / "contracts" / "codes.py").exists()
    assert not (PACKAGE / "contracts" / "http.py").exists()
    assert not (PACKAGE / "commons" / "shared" / "codes.py").exists()
    assert not list((PACKAGE / "commons" / "events").glob("*.py"))
    assert not list((PACKAGE / "interface" / "events").glob("*.py"))
    assert not (PACKAGE / "interface" / "shared" / "schemas.py").exists()
    assert not (PACKAGE / "interface" / "api" / "errors.py").exists()
    assert not (PACKAGE / "interface" / "application" / "errors.py").exists()
    assert not (PACKAGE / "interface" / "application" / "agents.py").exists()
    assert not (PACKAGE / "default_settings").exists()
    assert not (PACKAGE / "domain" / "llm" / "rules").exists()
    assert not (PACKAGE / "usecase" / "jobs" / "models.py").exists()
    assert not [
        path for path in (PACKAGE / "usecase" / "jobs").glob("_*.py") if path.name != "__init__.py"
    ]


def test_static_checks_do_not_broadly_ignore_application_or_api_layers() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "ignore_errors = true" not in pyproject


def _assert_public_surface(module: ModuleType, expected: set[str]) -> None:
    actual = set(module.__all__)

    assert actual == expected
    assert not [name for name in actual if name.startswith("_")]
    assert not [name for name in actual if not hasattr(module, name)]


def _imports_under(path: Path) -> list[tuple[Path, str]]:
    imported: list[tuple[Path, str]] = []
    for source_path in path.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend((source_path, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append((source_path, node.module))
    return imported
