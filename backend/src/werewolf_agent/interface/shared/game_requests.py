"""Shared request builders for public game API clients."""

from __future__ import annotations

from pydantic import ValidationError

from werewolf_agent.commons.shared.messages import (
    MESSAGE_ROLE_COUNT_MUST_BE_INTEGER,
    MESSAGE_ROLE_COUNT_MUST_USE_EQUALS,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    LocalRulesSettings,
    RoleId,
)


def build_create_game_request(
    *,
    seed: int | None,
    role_counts: dict[RoleId, int],
    human_player_id: str | None,
    rules: LocalRulesSettings | None = None,
) -> CreateGameRequest:
    """Build a public create-game request shared by CLI and Streamlit."""
    try:
        return CreateGameRequest(
            seed=seed,
            role_counts=role_counts,
            human_player_id=human_player_id,
            rules=rules,
        )
    except ValidationError as exc:
        detail = "; ".join(
            str(error.get("msg", "invalid create game request")) for error in exc.errors()
        )
        raise AppError(detail, code=ErrorCode.CONFIG_INVALID_VALUE) from exc


def parse_role_counts(entries: list[str]) -> dict[RoleId, int]:
    """Parse role=count entries into API role count payload values."""
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
        role_counts[key.strip()] = count
    return role_counts
