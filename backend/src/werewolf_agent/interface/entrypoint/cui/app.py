"""Command line interface entry point for Werewolf Agent."""

from __future__ import annotations

import logging

import typer
from pydantic import ValidationError

from werewolf_agent.commons.configuration import (
    configure_interface_logging,
    settings_error_detail,
)
from werewolf_agent.commons.shared.messages import (
    LOG_CLI_APPLICATION_STARTED,
    message_error_line,
)
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

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Werewolf Agent development and gameplay commands.",
    no_args_is_help=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Werewolf Agent command group."""
    try:
        settings = configure_interface_logging()
    except ValidationError as exc:
        error = ConfigError(settings_error_detail(exc))
        typer.echo(message_error_line(error.detail), err=True)
        raise typer.Exit(code=1) from exc
    logger.info(
        LOG_CLI_APPLICATION_STARTED,
        extra={
            "event_action": LOG_CLI_APPLICATION_STARTED,
            "event_outcome": "success",
            "cli_command": ctx.invoked_subcommand,
            "log_level": settings.log_level,
            "log_output": settings.log_output,
            "log_file_path": str(settings.log_file_path),
            "log_third_party_level": settings.log_third_party_level,
        },
    )


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
