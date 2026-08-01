"""Composeの設定配線と秘密情報境界。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"


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
    for service in ("api:", "streamlit:"):
        if service in compose:
            block = compose.split(service, maxsplit=1)[1].split("\n  ", maxsplit=1)[0]
            assert "OPENAI_API_KEY" not in block


def test_runtime_settings_are_wired_to_their_compose_services() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    api_block = compose.split("  api:", maxsplit=1)[1].split("\n  worker:", maxsplit=1)[0]
    worker_block = compose.split("  worker:", maxsplit=1)[1].split("\n  streamlit:", maxsplit=1)[0]
    streamlit_block = compose.split("  streamlit:", maxsplit=1)[1].split(
        "\n  test:",
        maxsplit=1,
    )[0]
    for setting in (
        "WEREWOLF_REVEAL_API_ENABLED",
        "WEREWOLF_API_DOCS_ENABLED",
        "WEREWOLF_API_CORS_ORIGINS",
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
        "WEREWOLF_WORKER_PAID_LLM_ENABLED",
        "WEREWOLF_WORKER_PAID_LLM_DAILY_ADVANCE_LIMIT",
        "WEREWOLF_WORKER_PAID_LLM_MAX_CONCURRENT_ADVANCES",
        "WEREWOLF_WORKER_PAID_LLM_ADMISSION_TTL_SECONDS",
    ):
        assert setting in worker_block
    for setting in (
        "WEREWOLF_SUPABASE_AUTH_TIMEOUT_SECONDS",
        "WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS",
        "WEREWOLF_STREAMLIT_AUTO_ADVANCE_INTERVAL_SECONDS",
    ):
        assert setting in streamlit_block

    reveal_default = "WEREWOLF_REVEAL_API_ENABLED: ${WEREWOLF_REVEAL_API_ENABLED:-false}"
    assert reveal_default in api_block
    assert reveal_default in worker_block


def test_compose_uses_a_container_reachable_database_dsn() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "WEREWOLF_SUPABASE_DB_DSN: ${WEREWOLF_COMPOSE_MIGRATION_DB_DSN:-}" in compose
    assert "WEREWOLF_SUPABASE_API_DB_DSN: ${WEREWOLF_COMPOSE_API_DB_DSN:-}" in compose
    assert "WEREWOLF_SUPABASE_WORKER_DB_DSN: ${WEREWOLF_COMPOSE_WORKER_DB_DSN:-}" in compose
    api_block = compose.split("  api:", maxsplit=1)[1].split("\n  worker:", maxsplit=1)[0]
    worker_block = compose.split("  worker:", maxsplit=1)[1].split("\n  streamlit:", maxsplit=1)[0]
    assert "WORKER_DB_DSN" not in api_block
    assert "API_DB_DSN" not in worker_block


def test_host_services_resolve_the_host_gateway_on_every_platform() -> None:
    """Docker DesktopとLinux runnerで同じhost名からlocal Supabaseへ接続する。"""
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert '"host.docker.internal:host-gateway"' in compose
    assert compose.count("<<: *host-access") == 5


def test_worker_graph_limit_matches_packaged_default() -> None:
    """Composeが有効なgraph上限を古い値で上書きしない。"""
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "WEREWOLF_LLM_GRAPH_MAX_STEPS" not in compose


def test_streamlit_compose_only_overrides_the_container_address() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    streamlit_block = compose.split("  streamlit:", maxsplit=1)[1].split(
        "\n  test:",
        maxsplit=1,
    )[0]

    assert '"--server.address=0.0.0.0"' in streamlit_block
    assert "--server.port" not in streamlit_block
    assert "--browser.gatherUsageStats" not in streamlit_block
