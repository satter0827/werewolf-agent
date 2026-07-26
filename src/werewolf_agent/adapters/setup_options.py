"""Setup-option projection for user clients."""

from __future__ import annotations

from typing import Any, cast

from werewolf_agent.adapters.application_bridge import (
    build_game_application_config,
    build_game_definitions,
    build_player_setup_definitions,
)
from werewolf_agent.application.models import GameSetupOptionsResult
from werewolf_agent.application.policy_catalog import PHASE_ORDER_OPTIONS, POLICY_OPTIONS
from werewolf_agent.application.setup_options import default_setup_options
from werewolf_agent.contracts.schemas import (
    AbilityDefinitionView,
    CharacterDefinitionView,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    RoleDefinitionView,
    RuleCompositionOptionsView,
    RuleCompositionSelection,
    RulePhaseOrderOptionView,
    RulePolicyOptionView,
    ScenarioDefinitionView,
    SetupPresetDefinitionView,
)
from werewolf_agent.settings import AppSettings


def get_local_setup_options(settings: AppSettings) -> GameSetupOptionsResponse:
    """Return setup metadata from packaged/configured definitions."""
    options = default_setup_options(
        build_game_application_config(settings),
        build_game_definitions(settings),
        build_player_setup_definitions(settings),
    )
    return setup_options_response(options, settings)


def setup_options_response(
    options: GameSetupOptionsResult,
    settings: AppSettings,
) -> GameSetupOptionsResponse:
    """Convert application setup metadata into the public wire schema."""
    return GameSetupOptionsResponse(
        player_count=options.player_count,
        roles=[
            RoleDefinitionView(
                id=role_id,
                name=str(definition.get("label") or role_id),
                identity_faction=str(definition["identity_faction"]),
                victory_team=str(definition["victory_team"]),
                objective=str(definition["objective"]),
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
        abilities=[
            AbilityDefinitionView(
                id=ability_id,
                name=str(definition["label"]),
                description=str(definition["description"]),
                phase=str(definition["phase"]),
                action=str(definition["action"]),
                validation_policy=str(definition["validation_policy"]),
                resolution_policy=str(definition["resolution_policy"]),
                target_policy=str(definition["target_policy"]),
                effect=str(definition["effect"]),
                max_uses=(
                    int(definition["max_uses"]) if definition.get("max_uses") is not None else None
                ),
                start_day=int(definition["start_day"]),
                result_visibility=cast(Any, str(definition.get("result_visibility") or "private")),
                resolution_priority=int(definition.get("resolution_priority") or 100),
                difficulty=int(definition["difficulty"]),
            )
            for ability_id, definition in options.abilities.items()
        ],
        scenarios=[
            ScenarioDefinitionView(
                id=scenario_id,
                name=str(definition["label"]),
                summary=str(definition["summary"]),
                premise=str(definition["prompt_premise"]),
                recommended_setup_preset=cast(
                    str | None,
                    definition.get("recommended_setup_preset"),
                ),
                role_names={
                    str(key): str(value)
                    for key, value in dict(definition.get("role_names") or {}).items()
                },
                role_objectives={
                    str(key): str(value)
                    for key, value in dict(definition.get("role_objectives") or {}).items()
                },
                faction_names={
                    str(key): str(value)
                    for key, value in dict(definition.get("faction_names") or {}).items()
                },
                ability_names={
                    str(key): str(value)
                    for key, value in dict(definition.get("ability_names") or {}).items()
                },
                action_names={
                    str(key): str(value)
                    for key, value in dict(definition.get("action_names") or {}).items()
                },
                phase_names={
                    str(key): str(value)
                    for key, value in dict(definition.get("phase_names") or {}).items()
                },
                narration={
                    str(event_type): tuple(str(item) for item in event["templates"])
                    for event_type, event in dict(
                        options.narration_profiles[str(definition["narration_profile"])]["events"]
                    ).items()
                },
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
        rule_composition=RuleCompositionOptionsView(
            default=RuleCompositionSelection.model_validate(options.rule_composition),
            phase_orders=[
                RulePhaseOrderOptionView.model_validate(item) for item in PHASE_ORDER_OPTIONS
            ],
            **{
                key: [RulePolicyOptionView.model_validate(item) for item in values]
                for key, values in POLICY_OPTIONS.items()
            },
        ),
    )
