"""CLIが記録するlog event名."""

from typing import Final

LOG_CLI_ACTION_SUBMITTED: Final = "cli.action.submitted"
LOG_CLI_APPLICATION_ERROR_HANDLED: Final = "cli.application_error.handled"
LOG_CLI_APPLICATION_STARTED: Final = "cli.application.started"
LOG_CLI_GAME_CREATED: Final = "cli.game.created"
LOG_CLI_PLAY_COMPLETED: Final = "cli.play.completed"
LOG_CLI_REPLAY_COMPLETED: Final = "cli.replay.completed"
LOG_CLI_TIMELINE_POLLED: Final = "cli.timeline.polled"
LOG_CLI_UNHANDLED_EXCEPTION: Final = "cli.exception.unhandled"

__all__ = [
    "LOG_CLI_ACTION_SUBMITTED",
    "LOG_CLI_APPLICATION_ERROR_HANDLED",
    "LOG_CLI_APPLICATION_STARTED",
    "LOG_CLI_GAME_CREATED",
    "LOG_CLI_PLAY_COMPLETED",
    "LOG_CLI_REPLAY_COMPLETED",
    "LOG_CLI_TIMELINE_POLLED",
    "LOG_CLI_UNHANDLED_EXCEPTION",
]
