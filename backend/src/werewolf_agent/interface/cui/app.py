"""Command line interface entry point for Werewolf Agent."""

from __future__ import annotations

import typer
from pydantic import ValidationError

from werewolf_agent.contracts import ConfigError
from werewolf_agent.interface.cui.commands import doctor, play
from werewolf_agent.interface.shared.runtime import (
    configure_interface_logging,
    settings_error_detail,
)

app = typer.Typer(
    help="Werewolf Agent development and gameplay commands.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Werewolf Agent command group."""
    try:
        configure_interface_logging()
    except ValidationError as exc:
        error = ConfigError(settings_error_detail(exc))
        typer.echo(f"Error: {error.detail}", err=True)
        raise typer.Exit(code=1) from exc


app.command(name="doctor")(doctor)
app.command(name="play")(play)


if __name__ == "__main__":
    app()
