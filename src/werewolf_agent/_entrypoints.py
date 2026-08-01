"""Optionalな提供層を遅延して起動するconsole entrypoint."""

from __future__ import annotations

from importlib.util import find_spec


def _require_extra(extra: str, modules: tuple[str, ...]) -> None:
    """不足するoptional依存があれば導入方法を示して終了する."""
    missing = tuple(module for module in modules if find_spec(module) is None)
    if not missing:
        return
    names = ", ".join(missing)
    raise SystemExit(
        f"{extra}機能の依存が不足しています: {names}\n"
        f"python -m pip install 'werewolf-agent[{extra}]'"
    )


def cli() -> None:
    """CLIを起動する."""
    _require_extra("cli", ("httpx", "pydantic", "rich", "typer"))
    from werewolf_agent.clients.cli.app import app

    app()


def api() -> None:
    """HTTP APIを起動する."""
    _require_extra("api", ("fastapi", "jwt", "psycopg", "pydantic_settings", "uvicorn"))
    from werewolf_agent.api.app import run

    run()


def worker() -> None:
    """非同期workerを起動する."""
    _require_extra("worker", ("langchain_core", "psycopg", "pydantic_settings", "typer"))
    from werewolf_agent.worker.app import app

    app()


__all__ = ["api", "cli", "worker"]
