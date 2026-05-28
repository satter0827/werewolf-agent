"""Command line interface entry point for Werewolf Agent."""

from __future__ import annotations

import typer
from pydantic import ValidationError

from werewolf_agent.commons.configuration import (
    configure_interface_logging,
    settings_error_detail,
)
from werewolf_agent.commons.shared.messages import message_error_line
from werewolf_agent.contracts import ConfigError
from werewolf_agent.interface.entrypoint.cui.commands import (
    create,
    doctor,
    play,
    replay,
    ruleset,
    runs,
    state,
    step,
    turns,
    watch,
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
        typer.echo(message_error_line(error.detail), err=True)
        raise typer.Exit(code=1) from exc


app.command(name="doctor")(doctor)
app.command(name="ruleset")(ruleset)
app.command(name="create")(create)
app.command(name="state")(state)
app.command(name="step")(step)
app.command(name="play")(play)
app.command(name="watch")(watch)
app.command(name="replay")(replay)
app.command(name="runs")(runs)
app.command(name="turns")(turns)


if __name__ == "__main__":
    app()
