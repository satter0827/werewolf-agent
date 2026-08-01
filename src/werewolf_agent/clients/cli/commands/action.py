"""Explicit manual action command."""

from __future__ import annotations

from typing import Annotated

import typer

from werewolf_agent.clients.cli.commands.common import _action_payload, _client, _output_format
from werewolf_agent.clients.cli.errors import run_app_command
from werewolf_agent.clients.cli.messages import HELP_OUTPUT_FORMAT
from werewolf_agent.clients.cli.output import print_json
from werewolf_agent.contracts.schemas import PLAYER_ACTION_REQUEST_ADAPTER
from werewolf_agent.settings import get_settings


def action(
    game_id: Annotated[str, typer.Argument(help="対象のgame ID")],
    player_id: Annotated[str, typer.Option("--player", help="操作するmanual player ID")],
    action_type: Annotated[str, typer.Option("--type", help="送信するaction ID")],
    ability_id: Annotated[
        str | None, typer.Option("--ability", help="use_abilityで使う能力ID")
    ] = None,
    target_id: Annotated[str | None, typer.Option("--target", help="対象player ID")] = None,
    message: Annotated[str | None, typer.Option(help="発言内容")] = None,
    reason: Annotated[str | None, typer.Option(help="公開する投票理由")] = None,
    response_to_id: Annotated[
        str | None, typer.Option("--response-to", help="応答する公開発言ID")
    ] = None,
    output: Annotated[str | None, typer.Option("--output", help=HELP_OUTPUT_FORMAT)] = None,
) -> None:
    """Submit one explicit action for a manual player."""
    settings = get_settings()
    run_app_command(
        lambda: print_json(
            _client().submit_player_action(
                game_id,
                player_id,
                PLAYER_ACTION_REQUEST_ADAPTER.validate_python(
                    _action_payload(
                        action_type,
                        ability_id=ability_id,
                        target_id=target_id,
                        message=message,
                        reason=reason,
                        response_to_id=response_to_id,
                    )
                ),
            ),
            output_format=_output_format(output, settings),
        )
    )


__all__ = ["action"]
