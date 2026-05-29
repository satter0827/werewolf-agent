"""Request builders shared by human-facing entry points."""

from __future__ import annotations

from typing import cast

from werewolf_agent.commons.shared.messages import (
    MESSAGE_HUMAN_PLAYER_ID_MUST_MATCH_PLAYERS,
    MESSAGE_ROLE_COUNT_MUST_BE_INTEGER,
    MESSAGE_ROLE_COUNT_MUST_USE_EQUALS,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGamePlayer,
    CreateGameRequest,
    CreateGameRuleConfig,
    RoleId,
    TieBreakPolicyId,
)


def build_create_game_request(
    *,
    players: int | None,
    seed: int | None,
    human_player: str | None,
    role_count: list[str],
    tie_break_policy: str,
    day_speech_turns: int,
    allow_self_vote: bool,
    default_player_count: int,
) -> CreateGameRequest:
    """Build a public create-game request for CLI and Streamlit entry points."""
    explicit_players = None
    if human_player is not None:
        player_count = players or default_player_count
        generated_player_ids = {f"player-{index}" for index in range(1, player_count + 1)}
        if human_player not in generated_player_ids:
            raise AppError(
                MESSAGE_HUMAN_PLAYER_ID_MUST_MATCH_PLAYERS,
                code=ErrorCode.CONFIG_INVALID_VALUE,
                context={"human_player": human_player, "player_count": player_count},
            )
        explicit_players = [
            CreateGamePlayer(
                id=f"player-{index}",
                name=f"Player {index}",
                agent_type="human" if f"player-{index}" == human_player else "llm",
            )
            for index in range(1, player_count + 1)
        ]
    rule_config = CreateGameRuleConfig(
        role_counts=parse_role_counts(role_count) or None,
        tie_break_policy=cast(TieBreakPolicyId, tie_break_policy),
        day_speech_turns=day_speech_turns,
        allow_self_vote=allow_self_vote,
    )
    return CreateGameRequest(
        player_count=None if explicit_players is not None else players,
        seed=seed,
        players=explicit_players,
        rule_config=rule_config,
    )


def parse_role_counts(entries: list[str]) -> dict[RoleId, int]:
    """Parse CLI-style role count entries into request schema values."""
    role_counts: dict[RoleId, int] = {}
    for entry in entries:
        key, separator, value = entry.partition("=")
        if separator == "":
            raise AppError(
                MESSAGE_ROLE_COUNT_MUST_USE_EQUALS,
                code=ErrorCode.CONFIG_INVALID_VALUE,
            )
        try:
            count = int(value)
        except ValueError as exc:
            raise AppError(
                MESSAGE_ROLE_COUNT_MUST_BE_INTEGER,
                code=ErrorCode.CONFIG_INVALID_VALUE,
            ) from exc
        role_counts[cast(RoleId, key.strip())] = count
    return role_counts
