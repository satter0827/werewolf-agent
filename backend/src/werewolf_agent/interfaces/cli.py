"""Command line interface for local development workflows."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from werewolf_agent.config import APP_NAME, get_settings, repository_root

app = typer.Typer(
    help="Werewolf Agent development and gameplay commands.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Werewolf Agent command group."""


def _package_version() -> str:
    try:
        return version(APP_NAME)
    except PackageNotFoundError:
        return "editable"


def _env_file_status(root: Path) -> str:
    env_path = root / ".env"
    example_path = root / ".env.example"

    if env_path.exists():
        return ".env found"
    if example_path.exists():
        return ".env missing; copy .env.example when enabling real providers"
    return ".env and .env.example missing"


@app.command()
def doctor() -> None:
    """Print local development environment diagnostics."""
    root = repository_root()
    settings = get_settings()

    table = Table(title="Werewolf Agent Doctor")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    table.add_row("package", f"{APP_NAME} {_package_version()}")
    table.add_row("python", sys.version.split()[0])
    table.add_row("python executable", sys.executable)
    table.add_row("platform", platform.platform())
    table.add_row("repository", str(root))
    table.add_row("env file", _env_file_status(root))
    table.add_row("provider", settings.llm_provider)
    table.add_row("model", settings.model)
    table.add_row("log level", settings.log_level)

    console.print(table)


if __name__ == "__main__":
    app()
