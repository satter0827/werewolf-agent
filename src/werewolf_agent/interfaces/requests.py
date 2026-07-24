"""Shared request builders for public game clients."""

from __future__ import annotations

from pydantic import ValidationError

from werewolf_agent.configuration.messages import (
    MESSAGE_INVALID_CREATE_GAME_REQUEST,
    MESSAGE_ROLE_COUNT_MUST_BE_INTEGER,
    MESSAGE_ROLE_COUNT_MUST_USE_EQUALS,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    LocalRulesSettings,
    NarrationMode,
    RoleId,
)


def build_create_game_request(
    *,
    seed: int | None,
    role_counts: dict[RoleId, int],
    manual_player_id: str | None,
    rules: LocalRulesSettings | None = None,
    scenario_id: str | None = None,
    setup_preset_id: str | None = None,
    agent_strategy_id: str | None = None,
    narration_mode: NarrationMode | None = None,
    character_assignments: dict[str, str] | None = None,
    custom_roles: list[CustomRoleDefinitionRequest] | None = None,
    custom_characters: list[CustomCharacterDefinitionRequest] | None = None,
) -> CreateGameRequest:
    """Build a public create-game request shared by CLI and Streamlit."""
    try:
        return CreateGameRequest(
            seed=seed,
            role_counts=role_counts,
            manual_player_id=manual_player_id,
            rules=rules,
            scenario_id=scenario_id,
            setup_preset_id=setup_preset_id,
            agent_strategy_id=agent_strategy_id,
            narration_mode=narration_mode,
            character_assignments=character_assignments or {},
            custom_roles=custom_roles or [],
            custom_characters=custom_characters or [],
        )
    except ValidationError as exc:
        detail = "; ".join(
            str(error.get("msg", MESSAGE_INVALID_CREATE_GAME_REQUEST)) for error in exc.errors()
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
