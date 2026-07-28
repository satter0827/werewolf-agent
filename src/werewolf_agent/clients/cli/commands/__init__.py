"""CLI commands grouped by user operation."""

from werewolf_agent.clients.cli.commands.doctor import (
    doctor,
)
from werewolf_agent.clients.cli.commands.games import (
    games,
    new,
    show,
)
from werewolf_agent.clients.cli.commands.play import (
    advance,
    play,
)
from werewolf_agent.clients.cli.commands.replay import (
    replay,
)
from werewolf_agent.clients.cli.commands.setup import (
    setup_options,
)
from werewolf_agent.clients.cli.commands.timeline import (
    timeline,
)

__all__ = [
    "advance",
    "doctor",
    "games",
    "new",
    "play",
    "replay",
    "setup_options",
    "show",
    "timeline",
]
