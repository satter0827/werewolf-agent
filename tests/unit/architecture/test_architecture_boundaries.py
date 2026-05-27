import ast
import inspect
from pathlib import Path

import werewolf_agent.usecase.jobs as game_jobs

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "backend" / "src" / "werewolf_agent"


def test_interfaces_do_not_import_domain_or_llm_directly() -> None:
    forbidden_prefixes = (
        "werewolf_agent.domain",
        "werewolf_agent.llm",
    )

    imported = _imports_under(PACKAGE / "interfaces")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_interfaces_import_only_public_usecase_jobs_from_application_bridge() -> None:
    imported = _imports_under(PACKAGE / "interfaces")
    application_path = PACKAGE / "interfaces" / "application"
    allowed_module = "werewolf_agent.usecase.jobs"

    assert not [
        (path, module)
        for path, module in imported
        if (module == "werewolf_agent.usecase" or module.startswith("werewolf_agent.usecase."))
        and (not path.is_relative_to(application_path) or module != allowed_module)
    ]


def test_api_routes_leave_game_id_parsing_to_usecase() -> None:
    urls_source = (PACKAGE / "interfaces" / "api" / "games" / "urls.py").read_text(encoding="utf-8")

    assert "<uuid:game_id>" not in urls_source
    assert "<str:game_id>" in urls_source


def test_usecase_jobs_public_surface_is_minimal() -> None:
    assert set(game_jobs.__all__) == {
        "AdvanceGameCommand",
        "AdvanceGameResult",
        "CreateGameCommand",
        "GameEventCreate",
        "GameNotFoundError",
        "GameRepository",
        "GameResult",
        "GameRunCreate",
        "GameRunUpdate",
        "GameUseCaseConfig",
        "GameUseCaseDependencies",
        "GetGameQuery",
        "InvalidGameIdError",
        "ListPublicEventsQuery",
        "PublicEventsResult",
        "RulesetResult",
        "StoredGameEvent",
        "StoredGameRun",
        "advance_game",
        "create_game",
        "get_default_ruleset",
        "get_game",
        "list_public_events",
    }


def test_usecase_jobs_are_stateless_command_or_query_functions() -> None:
    for function_name in ("create_game", "get_game", "advance_game", "list_public_events"):
        signature = inspect.signature(getattr(game_jobs, function_name))
        parameters = list(signature.parameters.values())

        assert len(parameters) == 2
        assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert parameters[1].name == "dependencies"
        assert parameters[1].kind is inspect.Parameter.KEYWORD_ONLY

    ruleset_signature = inspect.signature(game_jobs.get_default_ruleset)
    assert list(ruleset_signature.parameters) == ["config"]
    assert ruleset_signature.parameters["config"].kind is inspect.Parameter.KEYWORD_ONLY


def test_usecase_imports_domain_only_from_jobs() -> None:
    allowed_domain_modules = {
        "werewolf_agent.domain.models",
        "werewolf_agent.domain.service",
    }

    imported = _imports_under(PACKAGE / "usecase")
    jobs_path = PACKAGE / "usecase" / "jobs"
    bad_imports = []
    for path, module in imported:
        if not module.startswith("werewolf_agent.domain"):
            continue
        if not path.is_relative_to(jobs_path) or module not in allowed_domain_modules:
            bad_imports.append((path, module))

    assert not bad_imports


def test_commons_do_not_import_usecase_or_interfaces() -> None:
    forbidden_prefixes = (
        "werewolf_agent.usecase",
        "werewolf_agent.interfaces",
    )

    imported = _imports_under(PACKAGE / "commons")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


def test_domain_does_not_import_outer_layers() -> None:
    forbidden_prefixes = (
        "werewolf_agent.usecase",
        "werewolf_agent.interfaces",
        "werewolf_agent.commons",
        "werewolf_agent.llm",
    )

    imported = _imports_under(PACKAGE / "domain")

    assert not [
        (path, module)
        for path, module in imported
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden_prefixes)
    ]


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
