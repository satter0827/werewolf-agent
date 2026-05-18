"""Command line interface for local development workflows."""

from __future__ import annotations

import logging
import platform
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TypeVar

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from werewolf_agent.config import APP_NAME, get_settings, repository_root
from werewolf_agent.errors import AppError, ConfigError
from werewolf_agent.observation.logging import configure_logging

T = TypeVar("T")

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Werewolf Agent development and gameplay commands.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Werewolf Agent command group."""
    try:
        configure_logging(get_settings())
    except ValidationError as exc:
        error = ConfigError(_settings_error_detail(exc))
        typer.echo(f"Error: {error.detail}", err=True)
        raise typer.Exit(code=1) from exc


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


def run_app_command(command: Callable[[], T]) -> T:
    """Run one CLI command body with shared application error handling."""
    try:
        return command()
    except AppError as exc:
        logger.error("Command failed", extra=exc.log_extra())
        typer.echo(f"Error: {exc.detail}", err=True)
        raise typer.Exit(code=1) from exc


def _settings_error_detail(error: ValidationError) -> str:
    issues = error.errors()
    if not issues:
        return "Invalid application configuration."

    first_issue = issues[0]
    location = _settings_error_location(first_issue.get("loc", ()))
    message = str(first_issue.get("msg", "Invalid value."))
    return f"Invalid configuration for {location}: {message}"


def _settings_error_location(location: object) -> str:
    if isinstance(location, (tuple, list)):
        parts = [str(part) for part in location]
    elif location in (None, ""):
        parts = []
    else:
        parts = [str(location)]
    return ".".join(parts) if parts else "settings"


@app.command()
def doctor() -> None:
    """Print local development environment diagnostics."""
    run_app_command(_doctor)


def _doctor() -> None:
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
    table.add_row("log format", settings.log_format)
    table.add_row("log output", settings.log_output)

    console.print(table)


if __name__ == "__main__":
    app()
