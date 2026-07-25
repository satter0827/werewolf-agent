"""Command-line interface entry point for Werewolf Agent."""

from __future__ import annotations

import logging

import typer
from pydantic import ValidationError

from werewolf_agent.clients.cli.commands import (
    advance,
    doctor,
    games,
    new,
    play,
    replay,
    setup_options,
    show,
    timeline,
)
from werewolf_agent.clients.cli.events import (
    LOG_CLI_APPLICATION_STARTED,
)
from werewolf_agent.clients.cli.messages import (
    HELP_APP,
    message_error_line,
)
from werewolf_agent.contracts import ConfigError
from werewolf_agent.observability import configure_entrypoint_logging
from werewolf_agent.observability.constants import EVENT_OUTCOME_SUCCESS
from werewolf_agent.settings import (
    settings_error_detail,
)

logger = logging.getLogger(__name__)

app = typer.Typer(
    help=HELP_APP,
    no_args_is_help=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """Werewolf Agent command group."""
    try:
        settings = configure_entrypoint_logging(
            default_log_file_name="cli.jsonl",
            service_name="werewolf-agent-cli",
        )
    except ValidationError as exc:
        error = ConfigError(settings_error_detail(exc))
        typer.echo(message_error_line(error.detail), err=True)
        raise typer.Exit(code=1) from exc
    logger.info(
        LOG_CLI_APPLICATION_STARTED,
        extra={
            "event_action": LOG_CLI_APPLICATION_STARTED,
            "event_outcome": EVENT_OUTCOME_SUCCESS,
            "cli_command": ctx.invoked_subcommand,
            "log_level": settings.log_level,
            "log_output": settings.log_output,
            "log_file_path": str(settings.log_file_path),
            "log_third_party_level": settings.log_third_party_level,
        },
    )


app.command(name="doctor")(doctor)
app.command(name="setup-options")(setup_options)
app.command(name="new")(new)
app.command(name="show")(show)
app.command(name="advance")(advance)
app.command(name="play")(play)
app.command(name="timeline")(timeline)
app.command(name="replay")(replay)
app.command(name="games")(games)


if __name__ == "__main__":
    app()
