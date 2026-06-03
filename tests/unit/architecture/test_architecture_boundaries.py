import ast
import inspect
import json
from dataclasses import MISSING, fields
from pathlib import Path
from types import ModuleType

import werewolf_agent.domain.llm as llm_domain
import werewolf_agent.usecase.jobs as game_jobs
import werewolf_agent.usecase.jobs.games as game_job_models

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
    allowed_paths = (
        PACKAGE / "interface" / "application",
        PACKAGE / "interface" / "demo",
        PACKAGE / "interface" / "shared",
        PACKAGE / "interface" / "worker",
    )
    allowed_module = "werewolf_agent.usecase.jobs"

    assert not [
        (path, module)
        for path, module in imported
        if (module == "werewolf_agent.usecase" or module.startswith("werewolf_agent.usecase."))
        and (
            not any(path.is_relative_to(allowed_path) for allowed_path in allowed_paths)
            or module != allowed_module
        )
    ]


def test_api_routes_leave_game_id_parsing_to_usecase() -> None:
    router_source = (PACKAGE / "interface" / "api" / "routers.py").read_text(encoding="utf-8")

    assert "games" not in router_source
    assert "game_id: UUID" not in router_source


def test_usecase_jobs_public_surface_is_minimal() -> None:
    _assert_public_surface(
        game_jobs,
        {
            "CreateGameCommand",
            "AdvanceGameCommand",
            "AdvanceGameResult",
            "ComputedAdvanceGame",
            "GameEventCreate",
            "GameListResult",
            "GameRepository",
            "GameRecordCreate",
            "GameRecordUpdate",
            "GameResult",
            "GameRevealAction",
            "GameRevealInspection",
            "GameRevealNight",
            "GameRevealPlayer",
            "GameRevealResult",
            "GameRevealVote",
            "GameStatus",
            "GameUseCaseConfig",
            "GameUseCaseDependencies",
            "GameService",
            "GetGameQuery",
            "GetGameRevealQuery",
            "GetPlayerObservationQuery",
            "ListGamesQuery",
            "ListTimelineQuery",
            "LlmProviderConfig",
            "ManualPlayerCredential",
            "PlayerActionCommand",
            "PreparedAdvanceGame",
            "GameSetupOptionsResult",
            "StoredGameEvent",
            "StoredGame",
            "StoredGameSummary",
            "StoredGameTurn",
            "TelemetryEvent",
            "TelemetrySink",
        },
    )


def test_old_usecase_jobs_names_are_not_public() -> None:
    removed_names = {
        "AdvanceGameRunCommand",
        "AdvanceGameRunResult",
        "AdvanceUntilInputCommand",
        "AdvanceUntilInputResult",
        "CreateGameRunCommand",
        "GameRunCreate",
        "GameRunResult",
        "GameRunResponse",
        "GameRunUpdate",
        "GameRunsResponse",
        "GameUseCases",
        "GetGameRunQuery",
        "GetGameTimelineQuery",
        "ListGameRunsResult",
        "ListGameRunsQuery",
        "RulesetResult",
        "StoredGameRun",
        "StoredGameRunSummary",
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
            "AgentScenario",
            "AgentPlayerStatus",
            "LangChainDecisionProvider",
            "LlmDecisionProvider",
            "PlayerProfile",
            "PlayerProfileCatalog",
            "VisiblePlayer",
        },
    )


def test_usecase_jobs_expose_facade_instead_of_top_level_workflows() -> None:
    workflow_names = {
        "advance_game",
        "create_game",
        "get_game",
        "get_player_observation",
        "list_timeline",
        "list_games",
        "submit_player_action",
    }

    assert not [name for name in workflow_names if hasattr(game_jobs, name)]
    assert not hasattr(game_jobs.GameService, "advance_until_input")

    for method_name in workflow_names:
        signature = inspect.signature(getattr(game_jobs.GameService, method_name))
        parameters = list(signature.parameters.values())

        assert parameters[0].name == "self"
        assert all(parameter.name != "dependencies" for parameter in parameters)


def test_setup_options_metadata_does_not_require_repository_dependency() -> None:
    signature = inspect.signature(game_jobs.GameService.get_setup_options)
    assert list(signature.parameters) == [
        "config",
        "game_definitions",
        "llm_definitions",
    ]


def test_usecase_runtime_values_must_be_supplied_by_outer_layer() -> None:
    for model_type in (game_jobs.GameUseCaseConfig, game_jobs.LlmProviderConfig):
        for dataclass_field in fields(model_type):
            assert dataclass_field.default is MISSING
            assert dataclass_field.default_factory is MISSING

    dependency_fields = {
        dataclass_field.name: dataclass_field
        for dataclass_field in fields(game_jobs.GameUseCaseDependencies)
    }
    for field_name in ("config", "llm_provider_config"):
        assert dependency_fields[field_name].default is MISSING
        assert dependency_fields[field_name].default_factory is MISSING

    assert game_job_models.CreateGameCommand.model_fields["role_counts"].is_required()
    assert game_job_models.CreateGameCommand.model_fields["rules"].is_required()
    assert game_job_models.CreateGameCommand.model_fields["narration_mode"].is_required()
    assert (
        game_job_models.GameUseCaseConfig.__dataclass_fields__["default_setup_id"].default
        is MISSING
    )


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


def test_interface_application_bridge_has_no_stateful_db_adapter() -> None:
    app_source = (PACKAGE / "interface" / "api" / "app.py").read_text(encoding="utf-8")

    assert "app.state.game_application" not in app_source
    assert "sqlalchemy" not in app_source.lower()


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


def test_streamlit_setup_state_does_not_import_ui_or_inner_layers() -> None:
    forbidden_modules = (
        "rich",
        "streamlit",
        "typer",
        "werewolf_agent.domain",
        "werewolf_agent.interface.shared",
        "werewolf_agent.usecase",
    )

    imported = _imports_under(PACKAGE / "interface" / "entrypoint" / "streamlit")
    setup_imports = [(path, module) for path, module in imported if path.name == "setup.py"]

    assert not [
        (path, module)
        for path, module in setup_imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_streamlit_app_keeps_api_workflows_out_of_screen_assembly() -> None:
    app_source = (PACKAGE / "interface" / "entrypoint" / "streamlit" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "interface.shared" not in app_source
    assert "workflows." not in app_source
    assert "build_game_api_client" not in app_source


def test_streamlit_components_do_not_import_ui_or_api_workflows() -> None:
    forbidden_modules = (
        "streamlit",
        "werewolf_agent.domain",
        "werewolf_agent.interface.shared",
        "werewolf_agent.usecase",
    )

    imported = _imports_under(PACKAGE / "interface" / "entrypoint" / "streamlit")
    component_imports = [
        (path, module) for path, module in imported if path.name == "components.py"
    ]

    assert not [
        (path, module)
        for path, module in component_imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_vscode_launch_uses_open_workspace_without_branch_pinning() -> None:
    launch_source = (ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8")

    assert "${workspaceFolder}" in launch_source
    assert ".codex/worktrees" not in launch_source.replace("\\", "/")
    assert "refs/heads" not in launch_source


def test_vscode_launch_uses_temp_runtime_state() -> None:
    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    configurations = {
        configuration["name"]: configuration for configuration in launch["configurations"]
    }

    api_env = configurations["API: uvicorn"]["env"]
    worker_env = configurations["Worker: run"]["env"]
    streamlit_env = configurations["UI: Streamlit"]["env"]

    assert "WEREWOLF_SQLITE_PATH" not in api_env
    assert "WEREWOLF_STREAMLIT_API_URL" not in streamlit_env
    assert "WEREWOLF_STREAMLIT_SAVE_FILE" not in streamlit_env
    _assert_process_log_file_env(api_env, "api.jsonl")
    _assert_process_log_file_env(worker_env, "worker.jsonl")
    _assert_process_log_file_env(streamlit_env, "streamlit.jsonl")

    for name, configuration in configurations.items():
        env = configuration["env"]
        if name.startswith("CLI: "):
            _assert_process_log_file_env(env, "cli.jsonl")
        elif name.startswith("Pytest: "):
            assert "WEREWOLF_LOG_OUTPUT" not in env


def test_vscode_supabase_task_matches_runtime_state() -> None:
    tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    migrate_task = next(
        task for task in tasks["tasks"] if task["label"] == "Supabase: migration up"
    )

    assert migrate_task["args"] == [
        "migration",
        "up",
    ]
    _assert_process_log_file_env(migrate_task["options"]["env"], "migrate.jsonl")


def test_runtime_default_env_values_are_not_mirrored_by_tooling() -> None:
    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    env_blocks: list[dict[str, str]] = [
        configuration["env"] for configuration in launch["configurations"] if "env" in configuration
    ]
    env_blocks.extend(
        task["options"]["env"]
        for task in tasks["tasks"]
        if "options" in task and "env" in task["options"]
    )
    for env in env_blocks:
        _assert_no_runtime_default_log_mirror(env)

    text_sources = [
        (ROOT / "scripts" / "check-all.cmd").read_text(encoding="utf-8"),
        (ROOT / "scripts" / "run-api.cmd").read_text(encoding="utf-8"),
        (ROOT / "compose.yaml").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(text_sources)
    for key in RUNTIME_DEFAULT_LOG_ENV_KEYS:
        assert key not in combined
    assert "WEREWOLF_GAME_DEFAULT_" + "RULESET" not in combined
    assert "WEREWOLF_GAME_" + "RULESET" not in combined


def test_supabase_migration_enables_rls_and_admin_claims() -> None:
    migration_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "supabase" / "migrations").glob("*.sql")
    )

    assert "enable row level security" in migration_sources.lower()
    assert "auth.jwt() -> 'app_metadata'" in migration_sources
    assert "service_role" in migration_sources


def test_execution_helpers_route_operational_logs_to_workspace_log_dir() -> None:
    paths = [
        ROOT / ".vscode" / "launch.json",
        ROOT / ".vscode" / "tasks.json",
        ROOT / "scripts" / "check-all.cmd",
        ROOT / "scripts" / "run-api.cmd",
        ROOT / "compose.yaml",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "{temp}/werewolf-agent/logs" not in source
        assert "%TEMP%\\werewolf-agent\\logs" not in source
        assert "${env:TEMP}\\werewolf-agent\\logs" not in source


def test_operational_log_file_names_use_process_names_not_launcher_names() -> None:
    sources = [
        (ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"),
        (ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"),
        (ROOT / "scripts" / "check-all.cmd").read_text(encoding="utf-8"),
        (ROOT / "scripts" / "run-api.cmd").read_text(encoding="utf-8"),
        (ROOT / "compose.yaml").read_text(encoding="utf-8"),
        (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        (ROOT / "README.md").read_text(encoding="utf-8"),
        (ROOT / "docs" / "notes" / "development.md").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(sources)

    assert "vscode-api.jsonl" not in combined
    assert "vscode-streamlit.jsonl" not in combined
    assert "vscode-cli.jsonl" not in combined
    assert "vscode-migrate.jsonl" not in combined
    assert "codex-api.jsonl" not in combined
    assert "local-api.jsonl" not in combined
    assert "local.jsonl" not in combined
    assert "api.jsonl" in combined
    assert "streamlit.jsonl" in combined
    assert "cli.jsonl" in combined
    assert "migrate.jsonl" in combined
    assert "worker.jsonl" in combined


def test_log_defaults_are_documented_as_workspace_log_defaults() -> None:
    defaults_source = (
        ROOT / "backend" / "src" / "werewolf_agent" / "resources" / "settings" / "defaults.toml"
    ).read_text(encoding="utf-8")
    for key in (
        "log_level",
        "log_output",
        "log_dir",
        "log_file_name",
        "log_retention_days",
        "log_third_party_level",
    ):
        assert f"{key} =" in defaults_source

    for path in (ROOT / "README.md", ROOT / "docs" / "notes" / "development.md"):
        source = path.read_text(encoding="utf-8")
        assert ".werewolf-agent/logs/werewolf-agent.jsonl" in source
        assert "%TEMP%\\werewolf-agent\\logs" not in source
        assert "{temp}/werewolf-agent/logs" not in source


def test_user_facing_messages_are_catalogued() -> None:
    allowed_message_paths = {
        PACKAGE / "commons" / "shared" / "messages.py",
        PACKAGE / "interface" / "shared" / "messages.py",
        PACKAGE / "interface" / "entrypoint" / "cui" / "messages.py",
    }
    exception_message_calls = {
        "AppError",
        "ConfigError",
        "GameError",
        "ResourceNotFoundError",
        "RuntimeError",
        "ValueError",
    }
    cui_path = PACKAGE / "interface" / "entrypoint" / "cui"
    offenders: list[tuple[str, int, str]] = []

    for source_path in PACKAGE.rglob("*.py"):
        if source_path in allowed_message_paths:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _call_name(node.func)
            if (
                call_name in exception_message_calls
                and node.args
                and _is_string_message_literal(node.args[0])
            ):
                offenders.append(_message_offender(source_path, node, call_name))
            if call_name in {"Argument", "Option"}:
                for keyword in node.keywords:
                    if keyword.arg == "help" and _is_string_message_literal(keyword.value):
                        offenders.append(_message_offender(source_path, node, f"{call_name}.help"))
            if not source_path.is_relative_to(cui_path):
                continue
            if call_name == "Table":
                for keyword in node.keywords:
                    if keyword.arg == "title" and _is_string_message_literal(keyword.value):
                        offenders.append(_message_offender(source_path, node, "Table.title"))
            elif (
                call_name in {"add_column", "add_row", "fit", "print", "prompt"}
                and node.args
                and _is_string_message_literal(node.args[0])
            ):
                offenders.append(_message_offender(source_path, node, call_name))

    assert not offenders


def test_structured_log_outcomes_use_shared_constants() -> None:
    offenders: list[tuple[str, str]] = []
    for source_path in PACKAGE.rglob("*.py"):
        if source_path == PACKAGE / "commons" / "shared" / "constants.py":
            continue
        source = source_path.read_text(encoding="utf-8")
        for token in ('"event_outcome": "success"', '"event_outcome": "failure"'):
            if token in source:
                offenders.append((source_path.relative_to(ROOT).as_posix(), token))

    assert not offenders


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
        "werewolf_agent.commons.shared.definitions",
        "werewolf_agent.commons.shared.llm_tracing",
        "werewolf_agent.commons.shared.messages",
        "werewolf_agent.commons.shared.models",
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


def test_file_resource_loading_is_confined_to_interface_runtime() -> None:
    allowed_path = PACKAGE / "interface" / "runtime"
    forbidden_tokens = (
        "tomllib",
        "importlib.resources",
        "from importlib.resources",
        '.open("rb")',
        ".open('rb')",
    )
    offenders: list[tuple[Path, str]] = []

    for source_path in PACKAGE.rglob("*.py"):
        source = source_path.read_text(encoding="utf-8")
        if source_path.is_relative_to(allowed_path):
            continue
        offenders.extend((source_path, token) for token in forbidden_tokens if token in source)

    assert not offenders


def test_domain_and_usecase_do_not_depend_on_fixed_role_ids() -> None:
    forbidden_tokens = (
        "ROLE_VILLAGER",
        "ROLE_WEREWOLF",
        "ROLE_SEER",
        "ROLE_KNIGHT",
        "player_count - 3",
    )
    offenders: list[tuple[Path, str]] = []

    for base_path in (PACKAGE / "domain", PACKAGE / "usecase"):
        for source_path in base_path.rglob("*.py"):
            source = source_path.read_text(encoding="utf-8")
            offenders.extend((source_path, token) for token in forbidden_tokens if token in source)

    assert not offenders


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
    assert not (PACKAGE / "interface" / "entrypoint" / "shared").exists()
    assert not (PACKAGE / "interface" / "api" / "errors.py").exists()
    assert not (PACKAGE / "interface" / "application" / "errors.py").exists()
    assert not (PACKAGE / "interface" / "application" / "agents.py").exists()
    assert not (PACKAGE / "interface" / "shared" / "workflows.py").exists()
    assert not list((PACKAGE / "commons" / "configuration").glob("*.py"))
    assert not list((PACKAGE / "commons" / "observability").glob("*.py"))
    assert not (PACKAGE / "default_settings").exists()
    assert not (PACKAGE / "domain" / "llm" / "rules").exists()
    assert not (PACKAGE / "usecase" / "jobs" / "models.py").exists()
    assert not [
        path for path in (PACKAGE / "usecase" / "jobs").glob("_*.py") if path.name != "__init__.py"
    ]


def test_static_checks_do_not_broadly_ignore_application_or_api_layers() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "ignore_errors = true" not in pyproject


RUNTIME_DEFAULT_LOG_ENV_KEYS = (
    "WEREWOLF_LOG_LEVEL",
    "WEREWOLF_LOG_OUTPUT",
    "WEREWOLF_LOG_DIR",
    "WEREWOLF_LOG_RETENTION_DAYS",
    "WEREWOLF_LOG_THIRD_PARTY_LEVEL",
)


def _assert_process_log_file_env(env: dict[str, str], file_name: str) -> None:
    _assert_no_runtime_default_log_mirror(env)
    assert env["WEREWOLF_LOG_FILE_NAME"] == file_name


def _assert_no_runtime_default_log_mirror(env: dict[str, str]) -> None:
    for key in RUNTIME_DEFAULT_LOG_ENV_KEYS:
        assert key not in env


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


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_string_message_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(node.value.strip())
    )


def _message_offender(source_path: Path, node: ast.AST, call_name: str) -> tuple[str, int, str]:
    return (source_path.relative_to(ROOT).as_posix(), getattr(node, "lineno", 0), call_name)
