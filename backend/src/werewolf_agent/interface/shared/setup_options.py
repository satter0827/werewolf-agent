"""Shared setup-option projection for non-HTTP entry points."""

from __future__ import annotations

from typing import cast

import werewolf_agent.usecase.jobs as game_jobs
from werewolf_agent.contracts.schemas import (
    AbilityDefinitionView,
    AgentStrategyDefinitionView,
    CharacterDefinitionView,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    RoleDefinitionView,
    ScenarioDefinitionView,
    SetupPresetDefinitionView,
)
from werewolf_agent.interface.application.settings import (
    build_game_definitions,
    build_game_usecase_config,
    build_llm_definitions,
)
from werewolf_agent.interface.runtime import AppSettings


def get_local_setup_options(settings: AppSettings) -> GameSetupOptionsResponse:
    """Return setup metadata from packaged/configured definitions."""
    options = game_jobs.GameService.get_setup_options(
        build_game_usecase_config(settings),
        build_game_definitions(settings),
        build_llm_definitions(settings),
    )
    return setup_options_response(options, settings)


def setup_options_response(
    options: game_jobs.GameSetupOptionsResult,
    settings: AppSettings,
) -> GameSetupOptionsResponse:
    """Convert use case setup metadata into the public wire schema."""
    role_names = settings.game_role_name_map
    return GameSetupOptionsResponse(
        player_count=options.player_count,
        roles=[
            RoleDefinitionView(
                id=role_id,
                name=str(definition.get("label") or role_names.get(role_id, role_id)),
                faction=str(definition["faction"]),
                abilities=[str(ability) for ability in definition.get("abilities") or []],
                description=str(definition.get("description") or ""),
                difficulty=int(definition.get("difficulty") or 1),
            )
            for role_id, definition in options.roles.items()
        ],
        default_role_counts=options.default_role_counts,
        default_rules=LocalRulesSettings.model_validate(
            options.default_rules.model_dump(mode="json")
        ),
        default_scenario_id=options.default_scenario_id,
        default_setup_preset_id=options.default_setup_preset_id,
        default_narration_mode=options.default_narration_mode,
        default_agent_strategy_id=settings.llm_default_agent_strategy_id,
        abilities=[
            AbilityDefinitionView(
                id=ability_id,
                name=str(definition["label"]),
                description=str(definition["description"]),
                target_policy=str(definition["target_policy"]),
                difficulty=int(definition["difficulty"]),
            )
            for ability_id, definition in options.abilities.items()
        ],
        scenarios=[
            ScenarioDefinitionView(
                id=scenario_id,
                name=str(definition["label"]),
                summary=str(definition["summary"]),
                recommended_setup_preset=cast(
                    str | None,
                    definition.get("recommended_setup_preset"),
                ),
            )
            for scenario_id, definition in options.scenarios.items()
        ],
        setup_presets=[
            SetupPresetDefinitionView(
                id=preset_id,
                name=str(definition["label"]),
                scenario_id=str(definition["scenario_id"]),
                role_counts={
                    str(role_id): int(count)
                    for role_id, count in dict(definition["role_counts"]).items()
                },
            )
            for preset_id, definition in options.setup_presets.items()
        ],
        characters=[
            CharacterDefinitionView(
                id=character_id,
                name=str(definition["name"]),
                age=int(definition["age"]),
                gender=str(definition["gender"]),
                personality=str(definition["personality"]),
                speaking_style=str(definition["speaking_style"]),
                reasoning_style=str(definition["reasoning_style"]),
                risk_tolerance=str(definition["risk_tolerance"]),
            )
            for character_id, definition in options.characters.items()
        ],
        agent_strategies=[
            AgentStrategyDefinitionView(
                id=str(strategy_id),
                name=str(definition["name"]),
                description=str(definition["description"]),
            )
            for strategy_id, definition in options.agent_strategies.items()
        ],
    )
