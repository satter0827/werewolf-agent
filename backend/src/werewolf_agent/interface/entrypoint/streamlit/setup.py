"""Setup-state helpers for Streamlit game creation screens."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from werewolf_agent.contracts.schemas import (
    CharacterDefinitionView,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    LocalRulesSettings,
    NarrationMode,
    RoleDefinitionView,
    RulesetResponse,
    SetupPresetDefinitionView,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import I18nCatalog, Language

KEY_VIEW = "werewolf_streamlit_view"
KEY_SETUP_ROLE_COUNTS = "werewolf_streamlit_setup_role_counts"
KEY_SETUP_RULES = "werewolf_streamlit_setup_rules"
KEY_SETUP_PRESET = "werewolf_streamlit_setup_preset"
KEY_SETUP_SCENARIO = "werewolf_streamlit_setup_scenario"
KEY_SETUP_NARRATION_MODE = "werewolf_streamlit_setup_narration_mode"
KEY_SETUP_CHARACTER_ASSIGNMENTS = "werewolf_streamlit_setup_character_assignments"
KEY_SETUP_SEED = "werewolf_streamlit_setup_seed"
KEY_CUSTOM_ROLES = "werewolf_streamlit_custom_roles"
KEY_CUSTOM_CHARACTERS = "werewolf_streamlit_custom_characters"

VIEW_SETUP = "setup"
VIEW_OBSERVER_SETUP = "observer_setup"
VIEW_GAME = "game"
VIEW_SETTINGS = "settings"
VIEWS = frozenset({VIEW_SETUP, VIEW_OBSERVER_SETUP, VIEW_GAME, VIEW_SETTINGS})

PRESET_STANDARD = "standard"
PRESET_BEGINNER = "beginner"
PRESET_QUICK = "quick"
PRESET_LOGIC = "logic"
PRESETS = (PRESET_STANDARD, PRESET_BEGINNER, PRESET_QUICK, PRESET_LOGIC)
NARRATION_MODES: tuple[NarrationMode, ...] = ("standard", "rich", "none")


@dataclass(frozen=True)
class SetupValidation:
    """Validation result for one setup draft."""

    messages: list[str]

    @property
    def is_valid(self) -> bool:
        """Return whether the setup can create a game."""
        return not self.messages


def current_view(session: MutableMapping[str, Any]) -> str:
    """Return the selected Streamlit view."""
    view = str(session.get(KEY_VIEW, VIEW_SETUP))
    return view if view in VIEWS else VIEW_SETUP


def switch_view(session: MutableMapping[str, Any], view: str) -> None:
    """Switch the current Streamlit view."""
    session[KEY_VIEW] = view if view in VIEWS else VIEW_SETUP


def ruleset_with_session_customs(
    session: MutableMapping[str, Any],
    ruleset: RulesetResponse,
) -> RulesetResponse:
    """Return default ruleset values plus session-scoped custom definitions."""
    role_ids = {role.id for role in ruleset.roles}
    character_ids = {character.id for character in ruleset.characters}
    roles = list(ruleset.roles)
    roles.extend(
        RoleDefinitionView(
            id=definition.id,
            name=definition.name,
            faction=definition.faction,
            abilities=list(definition.abilities),
            description=definition.description,
            difficulty=definition.difficulty,
        )
        for definition in custom_roles(session)
        if definition.id not in role_ids
    )
    characters = list(ruleset.characters)
    characters.extend(
        CharacterDefinitionView.model_validate(definition.model_dump(mode="json"))
        for definition in custom_characters(session)
        if definition.id not in character_ids
    )
    return ruleset.model_copy(update={"roles": roles, "characters": characters})


def role_counts(session: MutableMapping[str, Any], ruleset: RulesetResponse) -> dict[str, int]:
    """Return role counts from session state or ruleset defaults."""
    raw_value = session.get(KEY_SETUP_ROLE_COUNTS)
    if not isinstance(raw_value, dict):
        defaults = preset_counts(selected_setup_preset_id(session, ruleset) or "", ruleset)
        return _counts_for_roles(defaults or ruleset.default_role_counts, ruleset.roles)
    counts = {
        role.id: max(0, int(raw_value.get(role.id, ruleset.default_role_counts.get(role.id, 0))))
        for role in ruleset.roles
    }
    return counts or _counts_for_roles(ruleset.default_role_counts, ruleset.roles)


def remember_role_counts(session: MutableMapping[str, Any], counts: Mapping[str, int]) -> None:
    """Store role counts in session state."""
    session[KEY_SETUP_ROLE_COUNTS] = {
        str(role_id): max(0, int(count)) for role_id, count in counts.items()
    }


def rules(session: MutableMapping[str, Any], ruleset: RulesetResponse) -> LocalRulesSettings:
    """Return active local rules from session state or ruleset defaults."""
    raw_value = session.get(KEY_SETUP_RULES)
    if not isinstance(raw_value, dict):
        return ruleset.default_rules
    return LocalRulesSettings.model_validate(raw_value)


def remember_rules(session: MutableMapping[str, Any], value: LocalRulesSettings) -> None:
    """Store active local rules in session state."""
    session[KEY_SETUP_RULES] = value.model_dump(mode="json")


def seed_text(session: MutableMapping[str, Any], default_seed: int) -> str:
    """Return the setup seed text."""
    return str(session.get(KEY_SETUP_SEED, default_seed))


def remember_seed_text(session: MutableMapping[str, Any], value: str) -> None:
    """Store the setup seed text."""
    session[KEY_SETUP_SEED] = value.strip()


def seed_from_text(value: str) -> int | None:
    """Return a parsed seed or None for an unfixed seed."""
    text = value.strip()
    return int(text) if text else None


def selected_setup_preset_id(
    session: MutableMapping[str, Any],
    ruleset: RulesetResponse,
) -> str | None:
    """Return the selected setup preset id."""
    preset_ids = {preset.id for preset in ruleset.setup_presets}
    raw_value = str(session.get(KEY_SETUP_PRESET, "")).strip()
    if raw_value in preset_ids:
        return raw_value
    if ruleset.default_setup_preset_id in preset_ids:
        return ruleset.default_setup_preset_id
    return ruleset.setup_presets[0].id if ruleset.setup_presets else None


def remember_setup_preset_id(session: MutableMapping[str, Any], value: str | None) -> None:
    """Store the selected setup preset id."""
    if value is None:
        session.pop(KEY_SETUP_PRESET, None)
        return
    session[KEY_SETUP_PRESET] = value


def selected_scenario_id(
    session: MutableMapping[str, Any],
    ruleset: RulesetResponse,
) -> str | None:
    """Return the selected scenario id."""
    scenario_ids = {scenario.id for scenario in ruleset.scenarios}
    raw_value = str(session.get(KEY_SETUP_SCENARIO, "")).strip()
    if raw_value in scenario_ids:
        return raw_value
    preset_id = selected_setup_preset_id(session, ruleset)
    preset = _setup_preset_by_id(ruleset, preset_id)
    if preset is not None and preset.scenario_id in scenario_ids:
        return preset.scenario_id
    if ruleset.default_scenario_id in scenario_ids:
        return ruleset.default_scenario_id
    return ruleset.scenarios[0].id if ruleset.scenarios else None


def remember_scenario_id(session: MutableMapping[str, Any], value: str | None) -> None:
    """Store the selected scenario id."""
    if value is None:
        session.pop(KEY_SETUP_SCENARIO, None)
        return
    session[KEY_SETUP_SCENARIO] = value


def narration_mode(session: MutableMapping[str, Any], ruleset: RulesetResponse) -> NarrationMode:
    """Return the selected public narration mode."""
    raw_value = str(session.get(KEY_SETUP_NARRATION_MODE, "")).strip()
    if raw_value in NARRATION_MODES:
        return raw_value
    return ruleset.default_narration_mode


def remember_narration_mode(session: MutableMapping[str, Any], value: NarrationMode) -> None:
    """Store the selected public narration mode."""
    session[KEY_SETUP_NARRATION_MODE] = value


def character_assignments(
    session: MutableMapping[str, Any],
    ruleset: RulesetResponse,
    *,
    player_count: int,
) -> dict[str, str]:
    """Return selected character ids keyed by generated player id."""
    raw_value = session.get(KEY_SETUP_CHARACTER_ASSIGNMENTS)
    if not isinstance(raw_value, dict):
        return {}
    valid_players = {f"player-{index}" for index in range(1, player_count + 1)}
    valid_characters = {character.id for character in ruleset.characters}
    return {
        str(player_id): str(character_id)
        for player_id, character_id in raw_value.items()
        if str(player_id) in valid_players and str(character_id) in valid_characters
    }


def remember_character_assignment(
    session: MutableMapping[str, Any],
    *,
    player_id: str,
    character_id: str | None,
) -> None:
    """Store one generated seat to character selection."""
    assignments = dict(session.get(KEY_SETUP_CHARACTER_ASSIGNMENTS, {}))
    if character_id is None:
        assignments.pop(player_id, None)
    else:
        assignments[player_id] = character_id
    session[KEY_SETUP_CHARACTER_ASSIGNMENTS] = assignments


def custom_roles(session: MutableMapping[str, Any]) -> list[CustomRoleDefinitionRequest]:
    """Return valid session-scoped custom role definitions."""
    raw_items = session.get(KEY_CUSTOM_ROLES)
    if not isinstance(raw_items, list):
        return []
    definitions: list[CustomRoleDefinitionRequest] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            definitions.append(CustomRoleDefinitionRequest.model_validate(item))
        except ValueError:
            continue
    return definitions


def custom_characters(session: MutableMapping[str, Any]) -> list[CustomCharacterDefinitionRequest]:
    """Return valid session-scoped custom character definitions."""
    raw_items = session.get(KEY_CUSTOM_CHARACTERS)
    if not isinstance(raw_items, list):
        return []
    definitions: list[CustomCharacterDefinitionRequest] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            definitions.append(CustomCharacterDefinitionRequest.model_validate(item))
        except ValueError:
            continue
    return definitions


def add_custom_role(
    session: MutableMapping[str, Any],
    *,
    name: str,
    faction: str,
    abilities: list[str],
    difficulty: int,
) -> None:
    """Append one custom role definition to the current session."""
    definition = CustomRoleDefinitionRequest(
        id=f"custom_role_{uuid4().hex[:10]}",
        name=name,
        faction=faction,
        abilities=abilities,
        description=_custom_role_description(faction, abilities),
        difficulty=difficulty,
    )
    session[KEY_CUSTOM_ROLES] = [
        item.model_dump(mode="json") for item in [*custom_roles(session), definition]
    ]


def add_custom_character(
    session: MutableMapping[str, Any],
    *,
    name: str,
    age: int,
    gender: str,
    personality: str,
    speaking_style: str,
    reasoning_style: str,
    risk_tolerance: str,
) -> None:
    """Append one custom character definition to the current session."""
    definition = CustomCharacterDefinitionRequest(
        id=f"custom_character_{uuid4().hex[:10]}",
        name=name,
        age=age,
        gender=gender,
        personality=personality,
        speaking_style=speaking_style,
        reasoning_style=reasoning_style,
        risk_tolerance=risk_tolerance,
    )
    session[KEY_CUSTOM_CHARACTERS] = [
        item.model_dump(mode="json") for item in [*custom_characters(session), definition]
    ]


def clear_custom_definitions(session: MutableMapping[str, Any]) -> None:
    """Remove all session-scoped custom definitions."""
    session.pop(KEY_CUSTOM_ROLES, None)
    session.pop(KEY_CUSTOM_CHARACTERS, None)
    session.pop(KEY_SETUP_CHARACTER_ASSIGNMENTS, None)


def preset_counts(preset: str, ruleset: RulesetResponse) -> dict[str, int]:
    """Return role counts for a named preset."""
    preset_definition = _setup_preset_by_id(ruleset, preset)
    if preset_definition is not None:
        return _counts_for_roles(preset_definition.role_counts, ruleset.roles)
    if preset == PRESET_STANDARD:
        return dict(ruleset.default_role_counts)
    if preset == PRESET_BEGINNER:
        return _balanced_counts(ruleset, total=ruleset.player_count["min"], include_guard=False)
    if preset == PRESET_QUICK:
        return _balanced_counts(ruleset, total=ruleset.player_count["min"], include_guard=False)
    if preset == PRESET_LOGIC:
        return _balanced_counts(
            ruleset,
            total=sum(ruleset.default_role_counts.values()),
            include_guard=True,
        )
    return dict(ruleset.default_role_counts)


def validate_setup(
    counts: Mapping[str, int],
    ruleset: RulesetResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> SetupValidation:
    """Validate role counts for the setup screen."""
    messages: list[str] = []
    total = sum(counts.values())
    min_players = ruleset.player_count["min"]
    max_players = ruleset.player_count["max"]
    if total < min_players or total > max_players:
        messages.append(catalog.t(lang, "setup.validation.total", min=min_players, max=max_players))

    known_role_ids = {role.id for role in ruleset.roles}
    unknown_roles = sorted(set(counts) - known_role_ids)
    if unknown_roles:
        messages.append(
            catalog.t(lang, "setup.validation.unknown_roles", roles=", ".join(unknown_roles))
        )

    if any(count < 0 for count in counts.values()):
        messages.append(catalog.t(lang, "setup.validation.negative"))

    if _faction_count(counts, ruleset.roles, "werewolf") < 1:
        messages.append(catalog.t(lang, "setup.validation.faction.werewolf"))
    if _faction_count(counts, ruleset.roles, "village") < 1:
        messages.append(catalog.t(lang, "setup.validation.faction.village"))
    return SetupValidation(messages=messages)


def seat_options(counts: Mapping[str, int]) -> list[tuple[str, str]]:
    """Return generated human seat options."""
    total = sum(counts.values())
    return [(f"player-{index}", f"P{index}") for index in range(1, total + 1)]


def setup_summary(
    counts: Mapping[str, int],
    *,
    rules: LocalRulesSettings,
    ruleset: RulesetResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return a compact setup summary."""
    role_parts = [
        f"{_role_name(role_id, ruleset, catalog, lang)} {count}"
        for role_id, count in counts.items()
        if count > 0
    ]
    tie_rule = catalog.t(
        lang,
        "setup.summary.tie.no_elimination"
        if rules.enable_no_elimination_on_tie
        else "setup.summary.tie.random_elimination",
    )
    first_night = catalog.t(
        lang,
        "setup.summary.first_night.on"
        if rules.enable_first_night_attack
        else "setup.summary.first_night.off",
    )
    return catalog.t(
        lang,
        "setup.summary",
        players=sum(counts.values()),
        roles=", ".join(role_parts),
        first_night=first_night,
        tie_rule=tie_rule,
    )


def _balanced_counts(
    ruleset: RulesetResponse,
    *,
    total: int,
    include_guard: bool,
) -> dict[str, int]:
    counts = {role.id: 0 for role in ruleset.roles}
    werewolf = _first_role(ruleset.roles, faction="werewolf")
    village = _first_role(ruleset.roles, faction="village", without_abilities=True) or _first_role(
        ruleset.roles,
        faction="village",
    )
    inspector = _first_role(ruleset.roles, ability="inspect")
    guard = _first_role(ruleset.roles, ability="guard") if include_guard else None
    for role in (werewolf, inspector, guard):
        if role is not None:
            counts[role.id] += 1
    filled = sum(counts.values())
    if village is not None and filled < total:
        counts[village.id] += total - filled
    return counts


def _counts_for_roles(counts: Mapping[str, int], roles: list[RoleDefinitionView]) -> dict[str, int]:
    return {role.id: max(0, int(counts.get(role.id, 0))) for role in roles}


def _role_name(
    role_id: str,
    ruleset: RulesetResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    for role in ruleset.roles:
        if role.id == role_id:
            return role.name
    return catalog.label(lang, "role", role_id)


def _setup_preset_by_id(
    ruleset: RulesetResponse,
    preset_id: str | None,
) -> SetupPresetDefinitionView | None:
    if preset_id is None:
        return None
    for preset in ruleset.setup_presets:
        if preset.id == preset_id:
            return preset
    return None


def _custom_role_description(faction: str, abilities: list[str]) -> str:
    ability_text = ", ".join(abilities) if abilities else "none"
    return f"faction={faction}; abilities={ability_text}"


def _first_role(
    roles: list[RoleDefinitionView],
    *,
    faction: str | None = None,
    ability: str | None = None,
    without_abilities: bool = False,
) -> RoleDefinitionView | None:
    for role in roles:
        if faction is not None and role.faction != faction:
            continue
        if ability is not None and ability not in role.abilities:
            continue
        if without_abilities and role.abilities:
            continue
        return role
    return None


def _faction_count(
    counts: Mapping[str, int],
    roles: list[RoleDefinitionView],
    faction: str,
) -> int:
    role_factions = {role.id: role.faction for role in roles}
    return sum(count for role_id, count in counts.items() if role_factions.get(role_id) == faction)
