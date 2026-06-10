import ast
import inspect
import json
from dataclasses import MISSING, fields
from pathlib import Path
from types import ModuleType

import werewolf_agent.api as public_api
import werewolf_agent.domain.llm as llm_domain
import werewolf_agent.usecase.jobs as game_jobs
import werewolf_agent.usecase.jobs.games as game_job_models

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "backend" / "src" / "werewolf_agent"


def test_interface_package_is_removed() -> None:
    assert not (PACKAGE / "interface").exists()


def test_top_level_layout_uses_api_entrypoint_commons_contracts() -> None:
    for package_name in ("api", "entrypoint", "commons", "contracts"):
        assert (PACKAGE / package_name / "__init__.py").exists()

    assert (PACKAGE / "api" / "supabase").is_dir()
    assert (PACKAGE / "api" / "local_demo").is_dir()
    assert (PACKAGE / "entrypoint" / "cui").is_dir()
    assert (PACKAGE / "entrypoint" / "streamlit").is_dir()


def test_entrypoints_do_not_import_domain_or_usecase_directly() -> None:
    forbidden_prefixes = (
        "werewolf_agent.domain",
        "werewolf_agent.usecase",
        "werewolf_agent.llm",
    )

    imported = _imports_under(PACKAGE / "entrypoint")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_api_usecase_imports_stay_in_adapters() -> None:
    imported = _imports_under(PACKAGE / "api")
    allowed_paths = (
        PACKAGE / "api" / "usecase_bridge.py",
        PACKAGE / "api" / "setup_options.py",
        PACKAGE / "api" / "telemetry.py",
        PACKAGE / "api" / "local_demo",
        PACKAGE / "api" / "supabase" / "worker",
    )

    offenders = []
    for path, module in imported:
        if not (module == "werewolf_agent.usecase" or module.startswith("werewolf_agent.usecase.")):
            continue
        if not any(
            path == allowed_path or path.is_relative_to(allowed_path)
            for allowed_path in allowed_paths
        ):
            offenders.append((path, module))

    assert not offenders


def test_api_does_not_depend_on_entrypoint_or_ui_libraries() -> None:
    forbidden_prefixes = (
        "rich",
        "streamlit",
        "werewolf_agent.entrypoint",
    )
    imported = _imports_under(PACKAGE / "api")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]

    typer_imports = [(path, module) for path, module in imported if module == "typer"]
    assert typer_imports == [(PACKAGE / "api" / "supabase" / "worker" / "app.py", "typer")]


def test_public_api_surface_is_minimal() -> None:
    _assert_public_surface(public_api, {"GameApi", "build_game_api"})


def test_usecase_jobs_public_surface_is_minimal() -> None:
    _assert_public_surface(
        game_jobs,
        {
            "AdvanceGameCommand",
            "AdvanceGameResult",
            "ComputedAdvanceGame",
            "CreateGameCommand",
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
            "GameService",
            "GameSetupOptionsResult",
            "GameStatus",
            "GameUseCaseConfig",
            "GameUseCaseDependencies",
            "GetGameQuery",
            "GetGameRevealQuery",
            "GetPlayerObservationQuery",
            "ListGamesQuery",
            "ListTimelineQuery",
            "LlmProviderConfig",
            "ManualPlayerCredential",
            "PlayerActionCommand",
            "PreparedAdvanceGame",
            "StoredGame",
            "StoredGameEvent",
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
            "AgentPlayerStatus",
            "AgentScenario",
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


def test_usecase_internal_does_not_import_outer_wire_or_api_layers() -> None:
    forbidden_prefixes = (
        "werewolf_agent.api",
        "werewolf_agent.entrypoint",
        "werewolf_agent.contracts.schemas",
    )

    imported = _imports_under(PACKAGE / "usecase" / "internal")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


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


def test_commons_do_not_import_inner_or_outer_layers() -> None:
    forbidden_prefixes = (
        "werewolf_agent.api",
        "werewolf_agent.domain",
        "werewolf_agent.entrypoint",
        "werewolf_agent.usecase",
    )

    imported = _imports_under(PACKAGE / "commons")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_contracts_do_not_import_api_frameworks_or_entrypoints() -> None:
    forbidden_modules = (
        "fastapi",
        "starlette",
        "sse_starlette",
        "typer",
        "streamlit",
        "werewolf_agent.api",
        "werewolf_agent.entrypoint",
    )

    imported = _imports_under(PACKAGE / "contracts")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_domain_does_not_import_outer_layers() -> None:
    allowed_commons_prefixes = ("werewolf_agent.commons.shared",)
    forbidden_prefixes = (
        "werewolf_agent.api",
        "werewolf_agent.contracts",
        "werewolf_agent.entrypoint",
        "werewolf_agent.usecase",
        "werewolf_agent.commons",
    )

    imported = _imports_under(PACKAGE / "domain")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
        and not any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in allowed_commons_prefixes
        )
    ]


def test_streamlit_view_models_do_not_import_ui_or_inner_layers() -> None:
    forbidden_modules = (
        "rich",
        "streamlit",
        "typer",
        "werewolf_agent.api",
        "werewolf_agent.domain",
        "werewolf_agent.usecase",
    )

    imported = _imports_under(PACKAGE / "entrypoint" / "streamlit")
    view_model_imports = [
        (path, module) for path, module in imported if path.name == "view_models.py"
    ]

    assert not [
        (path, module)
        for path, module in view_model_imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_streamlit_setup_state_and_components_do_not_import_inner_layers() -> None:
    forbidden_modules = (
        "rich",
        "streamlit",
        "typer",
        "werewolf_agent.api",
        "werewolf_agent.domain",
        "werewolf_agent.usecase",
    )

    imported = _imports_under(PACKAGE / "entrypoint" / "streamlit")
    checked_imports = [
        (path, module)
        for path, module in imported
        if path.name in {"setup.py", "state.py", "components.py"}
    ]

    assert not [
        (path, module)
        for path, module in checked_imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_modules)
    ]


def test_streamlit_app_keeps_api_workflows_out_of_screen_assembly() -> None:
    app_source = (PACKAGE / "entrypoint" / "streamlit" / "app.py").read_text(encoding="utf-8")

    assert "build_game_api" not in app_source
    assert "GameService" not in app_source
    assert "usecase" not in app_source


def test_vscode_launch_uses_current_entrypoints() -> None:
    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    configurations = {
        configuration["name"]: configuration for configuration in launch["configurations"]
    }

    assert "API: uvicorn" not in configurations
    assert configurations["Worker: run"]["module"] == "werewolf_agent.api.supabase.worker.app"
    assert (
        "backend/src/werewolf_agent/entrypoint/streamlit/app.py"
        in configurations["UI: Streamlit"]["args"]
    )
    assert launch["compounds"] == []


def test_vscode_launch_uses_process_log_files() -> None:
    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    configurations = {
        configuration["name"]: configuration for configuration in launch["configurations"]
    }

    _assert_process_log_file_env(configurations["Worker: run"]["env"], "worker.jsonl")
    _assert_process_log_file_env(configurations["UI: Streamlit"]["env"], "streamlit.jsonl")
    for name, configuration in configurations.items():
        env = configuration["env"]
        if name.startswith("CLI: "):
            _assert_process_log_file_env(env, "cli.jsonl")
        elif name.startswith("Pytest: "):
            assert "WEREWOLF_LOG_OUTPUT" not in env


def test_tooling_does_not_reference_fastapi_or_uvicorn() -> None:
    paths = [
        ROOT / "pyproject.toml",
        ROOT / "compose.yaml",
        ROOT / ".vscode" / "launch.json",
        ROOT / "docker" / "backend.Dockerfile",
        *sorted((ROOT / "scripts").glob("*.cmd")),
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths).lower()

    assert "fastapi" not in combined
    assert "uvicorn" not in combined
    assert "starlette" not in combined


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
        (ROOT / "compose.yaml").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(text_sources)
    for key in RUNTIME_DEFAULT_LOG_ENV_KEYS:
        assert key not in combined


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
        ROOT / "scripts" / "run-cli.cmd",
        ROOT / "scripts" / "run-worker.cmd",
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
        (ROOT / "scripts" / "run-cli.cmd").read_text(encoding="utf-8"),
        (ROOT / "scripts" / "run-worker.cmd").read_text(encoding="utf-8"),
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
    assert "streamlit.jsonl" in combined
    assert "cli.jsonl" in combined
    assert "migrate.jsonl" in combined
    assert "worker.jsonl" in combined


def test_file_resource_loading_is_confined_to_commons_resources() -> None:
    allowed_path = PACKAGE / "commons" / "resources.py"
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
        if source_path == allowed_path:
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
    assert not (PACKAGE / "interface").exists()
    assert not (PACKAGE / "entrypoint" / "api").exists()
    assert not (PACKAGE / "entrypoint" / "local_demo").exists()
    assert not (PACKAGE / "api" / "app.py").exists()
    assert not (PACKAGE / "api" / "routers.py").exists()
    assert not (PACKAGE / "api" / "messages.py").exists()
    assert not (ROOT / "scripts" / "run-api.cmd").exists()
    assert not (ROOT / "tests" / "integration" / "api" / "test_fastapi_health.py").exists()


def test_user_facing_messages_are_catalogued() -> None:
    allowed_message_paths = {
        PACKAGE / "commons" / "shared" / "messages.py",
        PACKAGE / "entrypoint" / "cui" / "messages.py",
    }
    exception_message_calls = {
        "AppError",
        "ConfigError",
        "GameError",
        "ResourceNotFoundError",
        "RuntimeError",
        "ValueError",
    }
    cui_path = PACKAGE / "entrypoint" / "cui"
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
