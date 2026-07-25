"""Executable architecture constraints for the application."""

from __future__ import annotations

from pathlib import Path

from scripts.architecture import (
    ALLOWED_IMPORTS,
    ALLOWED_PATH_IMPORTS,
    LAYERS,
    graph_cycles,
    imports_with_lines,
    module_name,
    project_import_edges,
)

import werewolf_agent.adapters as adapters
import werewolf_agent.agents as agents
import werewolf_agent.domain as domain
import werewolf_agent.usecase as usecase

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
FRONTEND = ROOT / "frontend" / "src"


def test_top_level_layout_has_independent_runtime_boundaries() -> None:
    for layer in LAYERS:
        assert (PACKAGE / layer).is_dir(), layer
    assert (ROOT / "frontend").is_dir()
    assert (ROOT / "frontend" / "e2e" / "react.spec.ts").is_file()
    assert (ROOT / "frontend" / "e2e" / "streamlit.spec.ts").is_file()
    assert (ROOT / "scripts" / "apply_migrations.py").is_file()
    assert (ROOT / "scripts" / "export_openapi.py").is_file()
    assert not (ROOT / "e2e").exists()
    assert not (ROOT / "tools").exists()
    assert not (PACKAGE / "interfaces" / "api").exists()
    assert (PACKAGE / "interfaces" / "worker" / "app.py").is_file()
    assert (PACKAGE / "interfaces" / "worker" / "service.py").is_file()
    assert not list((PACKAGE / "worker").rglob("*.py"))
    assert not list((PACKAGE / "adapters" / "supabase" / "worker").rglob("*.py"))
    assert not (PACKAGE / "adapters" / "supabase" / "game_client.py").exists()


def test_public_surfaces_are_minimal_and_explicit() -> None:
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
    assert set(usecase.__all__) == {"Actor", "GameApplication"}


def test_layer_imports_follow_the_allowed_matrix() -> None:
    offenders = [
        (edge.path, edge.source_layer, edge.target_layer)
        for edge in project_import_edges()
        if edge.target_layer not in ALLOWED_IMPORTS[edge.source_layer]
        and (edge.path, edge.target_layer) not in ALLOWED_PATH_IMPORTS
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
    factory = (PACKAGE / "adapters" / "factory.py").read_text(encoding="utf-8")
    assert "HttpGameClient" in factory
    assert "SupabaseGameClient" not in factory


def test_react_game_traffic_is_generated_http_and_supabase_is_auth_only() -> None:
    source_files = list(FRONTEND.rglob("*.ts")) + list(FRONTEND.rglob("*.tsx"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    data_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (FRONTEND / "data").rglob("*.ts")
    )
    assert "/rest/v1/" not in source
    assert ".from(" not in data_source
    assert "SupabaseGameClient" not in source
    assert "/api/v1/admin" not in data_source
    assert "openapi-fetch" in (FRONTEND / "data" / "ApiGameClient.ts").read_text(encoding="utf-8")
    assert (FRONTEND / "generated" / "api.ts").exists()
    supabase_importers = {
        path.relative_to(FRONTEND).as_posix()
        for path in source_files
        if "@supabase/supabase-js" in path.read_text(encoding="utf-8")
    }
    assert supabase_importers == {"data/AuthClient.ts"}


def test_frontend_test_runners_have_disjoint_scopes() -> None:
    vite_config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    playwright_config = (ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")
    assert 'include: ["src/**/*.test.{ts,tsx}"]' in vite_config
    assert 'testDir: process.env.PLAYWRIGHT_TEST_DIR ?? "e2e"' in playwright_config


def test_human_interface_client_port_excludes_administrator_operations() -> None:
    port = (PACKAGE / "adapters" / "ports.py").read_text(encoding="utf-8")
    http_client = (PACKAGE / "adapters" / "http" / "game_client.py").read_text(encoding="utf-8")
    assert "get_game_reveal" not in port
    assert "/api/v1/admin" not in http_client
    for path in (PACKAGE / "interfaces" / "streamlit").rglob("*.py"):
        assert "get_game_reveal" not in path.read_text(encoding="utf-8"), path


def test_react_responsive_layout_uses_public_runtime_breakpoint() -> None:
    layout = (FRONTEND / "features" / "village" / "VillageLayout.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "skins" / "dawn-table.css").read_text(encoding="utf-8")
    assert "runtimeConfig.ui.desktop_breakpoint" in layout
    assert "data-compact-layout={compactLayout}" in layout
    assert "@media (max-width:" not in css
    assert '.wa-app[data-compact-layout="true"]' in css


def test_action_text_limit_is_shared_by_api_react_and_streamlit() -> None:
    layout = (FRONTEND / "features" / "village" / "VillageLayout.tsx").read_text(encoding="utf-8")
    turn_panel = (FRONTEND / "features" / "village" / "components" / "TurnPanel.tsx").read_text(
        encoding="utf-8"
    )
    api_routes = (PACKAGE / "api" / "routes" / "games.py").read_text(encoding="utf-8")
    settings = (PACKAGE / "configuration" / "settings.py").read_text(encoding="utf-8")
    streamlit_app = (PACKAGE / "interfaces" / "streamlit" / "app.py").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "runtimeConfig.limits.message_max_chars" in layout
    assert "maxLength={messageMaxChars}" in turn_panel
    assert "maxLength={200}" not in turn_panel
    assert "_validate_action_text(request, services.message_max_chars)" in api_routes
    assert "runtime_config.limits.message_max_chars" in streamlit_app
    assert "max_chars=message_max_chars" in streamlit_app
    assert "max_chars=settings.api_message_max_chars" not in streamlit_app
    assert "WEREWOLF_API_MESSAGE_MAX_CHARS" in settings
    assert "WEREWOLF_STREAMLIT_MESSAGE_MAX_CHARS" not in settings
    api_client_environment = compose.split("services:", maxsplit=1)[0]
    assert "WEREWOLF_API_MESSAGE_MAX_CHARS" not in api_client_environment


def test_react_private_observation_is_scoped_to_play_mode() -> None:
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    assert 'activeView === "play" ? manualPlayerId : ""' in app
    assert '["game-screen", activeGameId, privatePlayerId]' in app
    assert "getScreen(activeGameId, privatePlayerId)" in app


def test_paid_provider_secret_is_worker_only_in_compose() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    occurrences = [
        line.strip()
        for line in compose.splitlines()
        if "OPENAI_API_KEY" in line and not line.lstrip().startswith("#")
    ]
    assert occurrences
    assert all("OPENAI_API_KEY" in line for line in occurrences)
    worker_block = compose.split("worker:", maxsplit=1)[1]
    assert "OPENAI_API_KEY" in worker_block
    for service in ("api:", "frontend:", "streamlit:"):
        if service in compose:
            block = compose.split(service, maxsplit=1)[1].split("\n  ", maxsplit=1)[0]
            assert "OPENAI_API_KEY" not in block


def test_runtime_settings_are_wired_to_their_compose_services() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    api_block = compose.split("  api:", maxsplit=1)[1].split("\n  worker:", maxsplit=1)[0]
    worker_block = compose.split("  worker:", maxsplit=1)[1].split(
        "\n  frontend:",
        maxsplit=1,
    )[0]
    streamlit_block = compose.split("  streamlit:", maxsplit=1)[1].split(
        "\n  test:",
        maxsplit=1,
    )[0]
    for setting in (
        "WEREWOLF_REVEAL_API_ENABLED",
        "WEREWOLF_API_DOCS_ENABLED",
        "WEREWOLF_API_MAX_BODY_BYTES",
        "WEREWOLF_API_RATE_LIMIT_WINDOW_SECONDS",
        "WEREWOLF_API_TIMEOUT_SECONDS",
        "WEREWOLF_API_MAX_CONCURRENT_REQUESTS",
    ):
        assert setting in api_block
    for setting in (
        "WEREWOLF_REVEAL_API_ENABLED",
        "WEREWOLF_SUPABASE_WORKER_BATCH_SIZE",
        "WEREWOLF_LLM_TIMEOUT_SECONDS",
        "WEREWOLF_WORKER_PAID_LLM_BASE_URL",
    ):
        assert setting in worker_block
    for setting in (
        "WEREWOLF_SUPABASE_AUTH_TIMEOUT_SECONDS",
        "WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS",
        "WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS",
    ):
        assert setting in streamlit_block


def test_compose_uses_a_container_reachable_database_dsn() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert compose.count("WEREWOLF_SUPABASE_DB_DSN: ${WEREWOLF_COMPOSE_SUPABASE_DB_DSN:-}") == 3
    assert "WEREWOLF_SUPABASE_DB_DSN: ${WEREWOLF_SUPABASE_DB_DSN:-}" not in compose


def test_api_entrypoint_uses_the_shared_redacting_log_pipeline() -> None:
    source = (PACKAGE / "api" / "app.py").read_text(encoding="utf-8")
    assert "configure_entrypoint_logging(" in source
    assert 'default_log_file_name="api.jsonl"' in source


def test_private_supabase_projections_are_not_data_api_tables() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260724000000_second_stage_baseline.sql"
    ).read_text(encoding="utf-8")
    for table in ("game_player_observations", "game_reveals"):
        assert f"alter table public.{table} set schema private" in migration
    assert "revoke all on all tables in schema private from anon, authenticated" in migration


def test_game_tables_are_unavailable_through_supabase_data_api() -> None:
    migration = (
        ROOT / "supabase" / "migrations" / "20260724000000_second_stage_baseline.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "games",
        "game_summaries",
        "game_participants",
        "game_public_turns",
        "game_operation_requests",
    ):
        assert f"revoke all on public.{table} from anon, authenticated" in migration
    cleanup_migration = (
        ROOT / "supabase" / "migrations" / "20260725000000_remove_legacy_public_tables.sql"
    ).read_text(encoding="utf-8")
    for legacy_table in (
        "profiles",
        "user_preferences",
        "definition_items",
        "retention_runs",
    ):
        assert f"drop table if exists public.{legacy_table}" in cleanup_migration
    rpc_cleanup = (
        ROOT / "supabase" / "migrations" / "20260725010000_remove_legacy_public_rpc.sql"
    ).read_text(encoding="utf-8")
    assert "drop function if exists public.is_admin() cascade" in rpc_cleanup
    for private_replacement in ("llm_invocations", "audit_events"):
        assert f"drop table if exists public.{private_replacement}" in migration


def test_streamlit_has_no_admin_reveal_path() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PACKAGE / "interfaces" / "streamlit").rglob("*.py")
    )
    assert "GameReveal" not in source
    assert "/admin" not in source


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


def test_domain_rules_and_fake_provider_remain_centralized() -> None:
    handlers = (PACKAGE / "usecase" / "handlers.py").read_text(encoding="utf-8")
    for legacy_function in ("start_game", "submit_action", "advance_phase", "observe"):
        assert f"{legacy_function}(" not in handlers
    service = (PACKAGE / "agents" / "langchain" / "service.py").read_text(encoding="utf-8")
    assert "from langchain_core.language_models.fake import FakeListLLM" in service
    assert "class Fake" not in service


def _imports(path: Path) -> set[str]:
    return {imported for imported, _ in imports_with_lines(path, module_name(path))}
