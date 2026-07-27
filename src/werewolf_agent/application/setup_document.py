"""Portable, validated definition of one complete game setup."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from werewolf_agent.application.definitions import (
    AbilityDefinition,
    CustomCharacterDefinition,
    GameDefinitions,
    LocalRulesDefinition,
    PlayerSetupDefinitions,
    RoleDefinition,
    RuleCompositionDefinition,
)
from werewolf_agent.application.models.base import ApplicationModel
from werewolf_agent.application.validation import non_blank

SETUP_SCHEMA_VERSION = 1
RoleCount = Annotated[int, Field(ge=0)]


class MechanicsDefinition(ApplicationModel):
    """Deterministic mechanics selected for one game."""

    role_counts: dict[str, RoleCount]
    roles: dict[str, RoleDefinition]
    abilities: dict[str, AbilityDefinition]
    rules: LocalRulesDefinition
    composition: RuleCompositionDefinition = Field(default_factory=RuleCompositionDefinition)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("role_counts")
    @classmethod
    def normalize_role_counts(cls, value: dict[str, int]) -> dict[str, int]:
        """Normalize selected role counts and discard zero-count catalog entries."""
        return {
            non_blank(str(key), "setup role id"): count for key, count in value.items() if count > 0
        }

    @field_validator("roles", "abilities")
    @classmethod
    def normalize_definition_ids(cls, value: dict[str, object]) -> dict[str, object]:
        """Normalize stable IDs used as definition mapping keys."""
        return {non_blank(str(key), "setup definition id"): item for key, item in value.items()}

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Reject incomplete or internally inconsistent mechanics."""
        if not self.role_counts or sum(self.role_counts.values()) < 1:
            raise ValueError("role_counts must select at least one player")
        unknown_roles = sorted(set(self.role_counts) - set(self.roles))
        if unknown_roles:
            raise ValueError(f"role_counts reference unknown roles: {unknown_roles}")
        unused_roles = sorted(set(self.roles) - set(self.role_counts))
        if unused_roles:
            raise ValueError(f"setup contains unused roles: {unused_roles}")
        referenced_abilities = {
            ability_id for role in self.roles.values() for ability_id in role.abilities
        }
        unknown_abilities = sorted(referenced_abilities - set(self.abilities))
        if unknown_abilities:
            raise ValueError(f"roles reference unknown abilities: {unknown_abilities}")
        unused_abilities = sorted(set(self.abilities) - referenced_abilities)
        if unused_abilities:
            raise ValueError(f"setup contains unused abilities: {unused_abilities}")
        selected_teams = {self.roles[role_id].victory_team for role_id in self.role_counts}
        if "village" not in selected_teams or "werewolf" not in selected_teams:
            raise ValueError("selected roles require village and werewolf victory teams")
        return self


class StoryThemeDefinition(ApplicationModel):
    """Presentation-only terminology and public narration for one setup."""

    id: str
    name: str
    summary: str
    premise: str
    role_names: dict[str, str]
    role_objectives: dict[str, str]
    faction_names: dict[str, str]
    ability_names: dict[str, str]
    action_names: dict[str, str]
    phase_names: dict[str, str]
    narration: dict[str, tuple[str, ...]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("id", "name", "summary", "premise")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Normalize required theme text."""
        return non_blank(value, "theme text")

    @field_validator(
        "role_names",
        "role_objectives",
        "faction_names",
        "ability_names",
        "action_names",
        "phase_names",
    )
    @classmethod
    def normalize_terms(cls, value: dict[str, str]) -> dict[str, str]:
        """Normalize stable IDs and their user-facing terms."""
        return {
            non_blank(str(key), "theme term id"): non_blank(text, "theme term")
            for key, text in value.items()
        }


class RosterDefinition(ApplicationModel):
    """Character definitions and optional fixed seat assignments."""

    characters: dict[str, CustomCharacterDefinition] = Field(default_factory=dict)
    assignments: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_assignments(self) -> Self:
        """Require unique, existing character assignments."""
        unknown = sorted(set(self.assignments.values()) - set(self.characters))
        if unknown:
            raise ValueError(f"assignments reference unknown characters: {unknown}")
        if len(set(self.assignments.values())) != len(self.assignments):
            raise ValueError("character assignments must be unique")
        return self


class GameSetupDocument(ApplicationModel):
    """Complete portable setup accepted by API, CLI, UI, and persistence."""

    schema_version: Literal[1] = 1
    mechanics: MechanicsDefinition
    theme: StoryThemeDefinition
    roster: RosterDefinition = Field(default_factory=RosterDefinition)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_theme_coverage(self) -> Self:
        """Require presentation terms for every selected mechanical concept."""
        selected_roles = {
            role_id for role_id, count in self.mechanics.role_counts.items() if count > 0
        }
        selected_abilities = {
            ability_id
            for role_id in selected_roles
            for ability_id in self.mechanics.roles[role_id].abilities
        }
        selected_factions = {
            faction
            for role_id in selected_roles
            for faction in (
                self.mechanics.roles[role_id].identity_faction,
                self.mechanics.roles[role_id].victory_team,
            )
        }
        selected_actions = {
            self.mechanics.abilities[ability_id].action for ability_id in selected_abilities
        } | {"speech", "vote", "pass"}
        required_phases = {"night", "day_discussion", "voting", "finished"}
        missing = {
            "roles": sorted(selected_roles - set(self.theme.role_names)),
            "role_objectives": sorted(selected_roles - set(self.theme.role_objectives)),
            "abilities": sorted(selected_abilities - set(self.theme.ability_names)),
            "factions": sorted(selected_factions - set(self.theme.faction_names)),
            "actions": sorted(selected_actions - set(self.theme.action_names)),
            "phases": sorted(required_phases - set(self.theme.phase_names)),
        }
        failures = {key: values for key, values in missing.items() if values}
        if failures:
            raise ValueError(f"theme does not cover selected mechanics: {failures}")
        extras = {
            "roles": sorted(set(self.theme.role_names) - selected_roles),
            "role_objectives": sorted(set(self.theme.role_objectives) - selected_roles),
            "abilities": sorted(set(self.theme.ability_names) - selected_abilities),
            "factions": sorted(set(self.theme.faction_names) - selected_factions),
            "actions": sorted(set(self.theme.action_names) - selected_actions),
            "phases": sorted(set(self.theme.phase_names) - required_phases),
        }
        extra_values = {key: values for key, values in extras.items() if values}
        if extra_values:
            raise ValueError(f"theme contains unused mechanics: {extra_values}")
        player_count = sum(self.mechanics.role_counts.values())
        if len(self.roster.characters) < player_count:
            raise ValueError("roster must provide at least one character per player")
        return self


class PresetSetupSelection(ApplicationModel):
    """Reference a packaged complete setup."""

    mode: Literal["preset"]
    preset_id: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class CustomSetupSelection(ApplicationModel):
    """Supply a complete setup inline."""

    mode: Literal["custom"]
    setup: GameSetupDocument

    model_config = ConfigDict(extra="forbid", frozen=True)


GameSetupSelection = Annotated[
    PresetSetupSelection | CustomSetupSelection,
    Field(discriminator="mode"),
]


def setup_document_from_preset(
    preset_id: str,
    definitions: GameDefinitions,
    player_definitions: PlayerSetupDefinitions,
) -> GameSetupDocument:
    """Resolve a packaged preset into the same complete document used by custom setup."""
    try:
        preset = definitions.catalog.setup_presets[preset_id]
    except KeyError as exc:
        raise ValueError(f"Unknown setup preset: {preset_id}") from exc
    scenario = definitions.catalog.scenarios[preset.scenario_id]
    profile = definitions.catalog.narration_profiles[scenario.narration_profile]
    selected_roles = {
        role_id: definitions.roles.roles[role_id]
        for role_id, count in preset.role_counts.items()
        if count > 0
    }
    selected_abilities = {
        ability_id for role in selected_roles.values() for ability_id in role.abilities
    }
    selected_factions = {
        faction
        for role in selected_roles.values()
        for faction in (role.identity_faction, role.victory_team)
    }
    selected_actions = {
        str(definitions.catalog.abilities[ability_id].action) for ability_id in selected_abilities
    } | {"speech", "vote", "pass"}
    mechanics = MechanicsDefinition(
        role_counts=dict(preset.role_counts),
        roles=selected_roles,
        abilities={
            ability_id: definitions.catalog.abilities[ability_id]
            for ability_id in selected_abilities
        },
        rules=definitions.rules.local_rules,
        composition=definitions.rules.composition,
    )
    theme = StoryThemeDefinition(
        id=preset.scenario_id,
        name=scenario.label,
        summary=scenario.summary,
        premise=scenario.prompt_premise,
        role_names={role_id: scenario.role_names[role_id] for role_id in selected_roles},
        role_objectives={role_id: scenario.role_objectives[role_id] for role_id in selected_roles},
        faction_names={
            faction_id: scenario.faction_names[faction_id] for faction_id in selected_factions
        },
        ability_names={
            ability_id: scenario.ability_names[ability_id] for ability_id in selected_abilities
        },
        action_names={
            action_id: scenario.action_names[action_id] for action_id in selected_actions
        },
        phase_names={
            phase_id: scenario.phase_names[phase_id]
            for phase_id in ("night", "day_discussion", "voting", "finished")
        },
        narration={event_type: event.templates for event_type, event in profile.events.items()},
    )
    characters = {
        character_id: CustomCharacterDefinition(
            id=character_id,
            name=profile.name,
            age=profile.age,
            gender=profile.gender,
            personality=profile.personality,
            speaking_style=profile.speaking_style,
            reasoning_style=profile.reasoning_style,
            risk_tolerance=profile.risk_tolerance,
            evidence_focus=profile.evidence_focus,
        )
        for character_id, profile in player_definitions.players.players.items()
    }
    return GameSetupDocument(
        mechanics=mechanics,
        theme=theme,
        roster=RosterDefinition(characters=characters),
    )


__all__ = [
    "SETUP_SCHEMA_VERSION",
    "CustomSetupSelection",
    "GameSetupDocument",
    "GameSetupSelection",
    "MechanicsDefinition",
    "PresetSetupSelection",
    "RosterDefinition",
    "StoryThemeDefinition",
    "setup_document_from_preset",
]
