"""Internal setup metadata helpers for game jobs."""

from __future__ import annotations

from collections.abc import Mapping

from werewolf_agent.commons.shared.definitions import GameDefinitions, LlmDefinitions
from werewolf_agent.usecase.jobs.games import GameSetupOptionsResult, GameUseCaseConfig


def default_setup_options(
    config: GameUseCaseConfig,
    definitions: GameDefinitions,
    llm_definitions: LlmDefinitions,
) -> GameSetupOptionsResult:
    """Return game setup business metadata."""
    default_setup_preset_id = _first_key(definitions.catalog.setup_presets)
    default_scenario_id = (
        definitions.catalog.setup_presets[default_setup_preset_id].scenario_id
        if default_setup_preset_id is not None
        else _first_key(definitions.catalog.scenarios)
    )
    return GameSetupOptionsResult(
        player_count={"min": config.min_players, "max": config.max_players},
        roles={
            role_id: definition.model_dump(mode="json")
            for role_id, definition in definitions.roles.roles.items()
        },
        default_role_counts=definitions.roles.default_counts_for(config.default_player_count),
        default_rules=definitions.rules.local_rules,
        default_scenario_id=default_scenario_id,
        default_setup_preset_id=default_setup_preset_id,
        default_narration_mode=config.default_narration_mode,
        default_agent_strategy_id=llm_definitions.agent_strategies.default_strategy_id,
        abilities={
            ability_id: definition.model_dump(mode="json")
            for ability_id, definition in definitions.catalog.abilities.items()
        },
        scenarios={
            scenario_id: definition.model_dump(mode="json")
            for scenario_id, definition in definitions.catalog.scenarios.items()
        },
        setup_presets={
            preset_id: definition.model_dump(mode="json")
            for preset_id, definition in definitions.catalog.setup_presets.items()
        },
        characters={
            character_id: definition.model_dump(mode="json")
            for character_id, definition in llm_definitions.players.players.items()
        },
        agent_strategies={
            strategy.id: {
                "name": strategy.name,
                "description": strategy.description,
            }
            for strategy in llm_definitions.agent_strategies.strategies
        },
    )


def _first_key(mapping: Mapping[str, object]) -> str | None:
    """Return the first stable key from a definition mapping."""
    return next(iter(mapping), None)
