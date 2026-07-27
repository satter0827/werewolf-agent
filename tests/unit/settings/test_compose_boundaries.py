"""Composeの設定配線と秘密情報境界。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "werewolf_agent"
FRONTEND = ROOT / "frontend" / "src"


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


def test_worker_graph_limit_matches_packaged_default() -> None:
    """Composeが有効なgraph上限を古い値で上書きしない。"""
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "WEREWOLF_LLM_GRAPH_MAX_STEPS:-16" in compose
