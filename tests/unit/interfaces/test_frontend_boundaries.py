"""Frontendと人向けinterfaceの構造契約。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
FRONTEND = ROOT / "frontend" / "src"


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


def test_streamlit_has_no_admin_reveal_path() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PACKAGE / "interfaces" / "streamlit").rglob("*.py")
    )
    assert "GameReveal" not in source
    assert "/admin" not in source
