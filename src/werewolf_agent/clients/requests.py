"""Shared request builders for public game clients."""

from __future__ import annotations

from typing import Any, cast

from pydantic import ValidationError

from werewolf_agent.clients.messages import (
    MESSAGE_INVALID_CREATE_GAME_REQUEST,
    MESSAGE_ROLE_COUNT_MUST_BE_INTEGER,
    MESSAGE_ROLE_COUNT_MUST_USE_EQUALS,
)
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.errors import ErrorCode
from werewolf_agent.contracts.schemas import (
    CreateGameRequest,
    CustomCharacterDefinitionRequest,
    CustomSetupRequest,
    GameSetupDocumentRequest,
    GameSetupOptionsResponse,
    GameSetupSelectionRequest,
    LocalRulesSettings,
    NarrationMode,
    RoleId,
    RuleCompositionSelection,
    SetupAbilityDefinition,
    SetupMechanicsSettings,
    SetupRoleDefinition,
    SetupRosterSettings,
    StoryThemeSettings,
)


def build_create_game_request(
    *,
    seed: int | None,
    manual_player_id: str | None,
    setup: GameSetupSelectionRequest,
    narration_mode: NarrationMode,
) -> CreateGameRequest:
    """Build a public create-game request shared by CLI and Streamlit."""
    try:
        return CreateGameRequest(
            seed=seed,
            manual_player_id=manual_player_id,
            setup=setup,
            narration_mode=narration_mode,
        )
    except ValidationError as exc:
        detail = "; ".join(
            str(error.get("msg", MESSAGE_INVALID_CREATE_GAME_REQUEST)) for error in exc.errors()
        )
        raise AppError(detail, code=ErrorCode.CONFIG_INVALID_VALUE) from exc


def build_custom_setup_request(
    *,
    setup_options: GameSetupOptionsResponse,
    role_counts: dict[RoleId, int],
    rules: LocalRulesSettings,
    scenario_id: str,
    character_assignments: dict[str, str],
    rule_composition: RuleCompositionSelection,
) -> CustomSetupRequest:
    """Build one complete custom setup from server-provided editing metadata."""
    scenario = next(item for item in setup_options.scenarios if item.id == scenario_id)
    selected_role_ids = {role_id for role_id, count in role_counts.items() if count > 0}
    all_roles = {
        role.id: SetupRoleDefinition(
            identity_faction=cast(Any, role.identity_faction),
            victory_team=cast(Any, role.victory_team),
            objective=role.objective,
            abilities=tuple(role.abilities),
            label=role.name,
            description=role.description,
            difficulty=role.difficulty,
        )
        for role in setup_options.roles
    }
    roles = {role_id: all_roles[role_id] for role_id in selected_role_ids}
    selected_ability_ids = {
        ability_id for role_id in selected_role_ids for ability_id in roles[role_id].abilities
    }
    all_abilities = {
        ability.id: SetupAbilityDefinition(
            phase=ability.phase,
            action=ability.action,
            validation_policy=ability.validation_policy,
            resolution_policy=ability.resolution_policy,
            target_policy=ability.target_policy,
            effect=cast(Any, ability.effect),
            start_day=ability.start_day,
            label=ability.name,
            description=ability.description,
            difficulty=ability.difficulty,
            max_uses=ability.max_uses,
            result_visibility=ability.result_visibility,
            resolution_priority=ability.resolution_priority,
        )
        for ability in setup_options.abilities
    }
    abilities = {ability_id: all_abilities[ability_id] for ability_id in selected_ability_ids}
    selected_factions = {
        faction for role in roles.values() for faction in (role.identity_faction, role.victory_team)
    }
    selected_actions = {abilities[ability_id].action for ability_id in selected_ability_ids} | {
        "speech",
        "vote",
        "pass",
    }
    characters = {
        character.id: CustomCharacterDefinitionRequest.model_validate(
            character.model_dump(mode="json")
        )
        for character in setup_options.characters
    }
    role_names = {
        role_id: scenario.role_names.get(role_id, roles[role_id].label)
        for role_id in selected_role_ids
    }
    role_objectives = {
        role_id: scenario.role_objectives.get(role_id, roles[role_id].objective)
        for role_id in selected_role_ids
    }
    ability_names = {
        ability_id: scenario.ability_names.get(ability_id, abilities[ability_id].label)
        for ability_id in selected_ability_ids
    }
    return CustomSetupRequest(
        mode="custom",
        setup=GameSetupDocumentRequest(
            mechanics=SetupMechanicsSettings(
                role_counts={role_id: role_counts[role_id] for role_id in selected_role_ids},
                roles=roles,
                abilities=abilities,
                rules=rules,
                composition=rule_composition,
            ),
            theme=StoryThemeSettings(
                id=scenario.id,
                name=scenario.name,
                summary=scenario.summary,
                premise=scenario.premise,
                role_names=role_names,
                role_objectives=role_objectives,
                faction_names={
                    faction_id: scenario.faction_names[faction_id]
                    for faction_id in selected_factions
                },
                ability_names=ability_names,
                action_names={
                    action_id: scenario.action_names[action_id] for action_id in selected_actions
                },
                phase_names={
                    phase_id: scenario.phase_names[phase_id]
                    for phase_id in ("night", "day_discussion", "voting", "finished")
                },
                narration=scenario.narration,
            ),
            roster=SetupRosterSettings(
                characters=characters,
                assignments=character_assignments,
            ),
        ),
    )


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
