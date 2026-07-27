"""Setup-state helpers for Streamlit game creation screens."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from werewolf_agent.clients.streamlit.constants import (
    NARRATION_MODE_NONE,
    NARRATION_MODE_STANDARD,
)
from werewolf_agent.clients.streamlit.i18n import I18nCatalog, Language
from werewolf_agent.contracts.schemas import (
    CharacterDefinitionView,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    NarrationMode,
    RoleDefinitionView,
    SetupPresetDefinitionView,
)
from werewolf_agent.settings.validation import (
    generated_player_id,
    generated_player_ids,
    public_generated_player_label,
)

KEY_CURRENT_VIEW = "werewolf_streamlit_current_view"
KEY_PENDING_VIEW_SCROLL = "werewolf_streamlit_pending_view_scroll"
KEY_GAME_SETUP_DRAFT = "werewolf_streamlit_game_setup_draft"
KEY_CUSTOM_ROLE_DEFINITIONS = "werewolf_streamlit_custom_role_definitions"
KEY_CUSTOM_CHARACTER_DEFINITIONS = "werewolf_streamlit_custom_character_definitions"
KEY_ROLE_COUNT_WIDGET_PREFIX = "werewolf_streamlit_game_setup_role_count"

VIEW_PLAY_SETUP = "play_setup"
VIEW_OBSERVE_SETUP = "observe_setup"
VIEW_HISTORY = "history"
VIEW_GAME = "game"
VIEW_APP_SETTINGS = "app_settings"
VIEW_ADMIN = "admin"
VIEWS = frozenset(
    {
        VIEW_PLAY_SETUP,
        VIEW_OBSERVE_SETUP,
        VIEW_HISTORY,
        VIEW_GAME,
        VIEW_APP_SETTINGS,
        VIEW_ADMIN,
    }
)

CUSTOM_ROLE_NO_ABILITIES_TEXT = "none"
NARRATION_MODES: tuple[NarrationMode, ...] = (
    NARRATION_MODE_STANDARD,
    NARRATION_MODE_NONE,
)


class GameSetupDraft(BaseModel):
    """Session-scoped draft for one game creation form."""

    role_counts: dict[str, int] = Field(default_factory=dict)
    rules: LocalRulesSettings | None = None
    setup_preset_id: str | None = None
    scenario_id: str | None = None
    narration_mode: NarrationMode | None = None
    character_assignments: dict[str, str] = Field(default_factory=dict)
    seed_text: str | None = None
    manual_player_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("role_counts", mode="before")
    @classmethod
    def normalize_role_counts(cls, value: object) -> dict[str, int]:
        """Return non-negative role counts keyed by role id."""
        if not isinstance(value, Mapping):
            return {}
        return {str(role_id): max(0, int(count)) for role_id, count in value.items()}

    @field_validator("character_assignments", mode="before")
    @classmethod
    def normalize_character_assignments(cls, value: object) -> dict[str, str]:
        """Return non-empty character assignments keyed by generated player id."""
        if not isinstance(value, Mapping):
            return {}
        return {
            str(player_id): str(character_id)
            for player_id, character_id in value.items()
            if str(player_id).strip() and str(character_id).strip()
        }

    @field_validator("setup_preset_id", "scenario_id", "manual_player_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Return stripped optional text fields."""
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @field_validator("seed_text")
    @classmethod
    def normalize_seed_text(cls, value: str | None) -> str | None:
        """Return stripped seed text while preserving an intentional blank."""
        if value is None:
            return None
        return str(value).strip()


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
    view = str(session.get(KEY_CURRENT_VIEW, VIEW_PLAY_SETUP))
    return view if view in VIEWS else VIEW_PLAY_SETUP


def switch_view(session: MutableMapping[str, Any], view: str) -> None:
    """Switch the current Streamlit view."""
    next_view = view if view in VIEWS else VIEW_PLAY_SETUP
    if current_view(session) == next_view:
        return
    session[KEY_CURRENT_VIEW] = next_view
    session[KEY_PENDING_VIEW_SCROLL] = True


def consume_pending_view_scroll(session: MutableMapping[str, Any]) -> bool:
    """Consume the one-shot scroll reset requested by a view transition."""
    return bool(session.pop(KEY_PENDING_VIEW_SCROLL, False))


def game_setup_draft(session: MutableMapping[str, Any]) -> GameSetupDraft:
    """Return the current game setup draft."""
    raw_value = session.get(KEY_GAME_SETUP_DRAFT)
    if not isinstance(raw_value, dict):
        return GameSetupDraft()
    try:
        return GameSetupDraft.model_validate(raw_value)
    except ValueError:
        return GameSetupDraft()


def remember_game_setup_draft(
    session: MutableMapping[str, Any],
    draft: GameSetupDraft,
) -> None:
    """Store the current game setup draft."""
    session[KEY_GAME_SETUP_DRAFT] = draft.model_dump(mode="json", exclude_none=True)


def setup_options_with_session_customs(
    session: MutableMapping[str, Any],
    setup_options: GameSetupOptionsResponse,
) -> GameSetupOptionsResponse:
    """Return default setup_options values plus session-scoped custom definitions."""
    role_ids = {role.id for role in setup_options.roles}
    character_ids = {character.id for character in setup_options.characters}
    roles = list(setup_options.roles)
    roles.extend(
        RoleDefinitionView(
            id=definition.id,
            name=definition.name,
            identity_faction=definition.identity_faction,
            victory_team=definition.victory_team,
            objective=definition.objective,
            abilities=list(definition.abilities),
            description=definition.description,
            difficulty=definition.difficulty,
        )
        for definition in custom_roles(session)
        if definition.id not in role_ids
    )
    characters = list(setup_options.characters)
    characters.extend(
        CharacterDefinitionView.model_validate(definition.model_dump(mode="json"))
        for definition in custom_characters(session)
        if definition.id not in character_ids
    )
    return setup_options.model_copy(update={"roles": roles, "characters": characters})


def role_counts(
    session: MutableMapping[str, Any], setup_options: GameSetupOptionsResponse
) -> dict[str, int]:
    """Return role counts from the game setup draft or setup_options defaults."""
    draft = game_setup_draft(session)
    if not draft.role_counts:
        defaults = preset_counts(
            selected_setup_preset_id(session, setup_options) or "", setup_options
        )
        return _counts_for_roles(defaults or setup_options.default_role_counts, setup_options.roles)
    counts = {
        role.id: max(
            0,
            int(draft.role_counts.get(role.id, setup_options.default_role_counts.get(role.id, 0))),
        )
        for role in setup_options.roles
    }
    return counts or _counts_for_roles(setup_options.default_role_counts, setup_options.roles)


def remember_role_counts(session: MutableMapping[str, Any], counts: Mapping[str, int]) -> None:
    """Store role counts in the game setup draft."""
    next_counts = {str(role_id): max(0, int(count)) for role_id, count in counts.items()}
    draft = game_setup_draft(session).model_copy(update={"role_counts": next_counts})
    remember_game_setup_draft(session, draft)


def rules(
    session: MutableMapping[str, Any], setup_options: GameSetupOptionsResponse
) -> LocalRulesSettings:
    """Return active local rules from the game setup draft or setup_options defaults."""
    return game_setup_draft(session).rules or setup_options.default_rules


def remember_rules(session: MutableMapping[str, Any], value: LocalRulesSettings) -> None:
    """Store active local rules in the game setup draft."""
    draft = game_setup_draft(session).model_copy(update={"rules": value})
    remember_game_setup_draft(session, draft)


def seed_text(session: MutableMapping[str, Any], default_seed: int) -> str:
    """Return the setup seed text."""
    draft_seed = game_setup_draft(session).seed_text
    return str(default_seed) if draft_seed is None else draft_seed


def remember_seed_text(session: MutableMapping[str, Any], value: str) -> None:
    """Store the setup seed text."""
    draft = game_setup_draft(session).model_copy(update={"seed_text": value.strip()})
    remember_game_setup_draft(session, draft)


def seed_from_text(value: str) -> int | None:
    """Return a parsed seed or None for an unfixed seed."""
    text = value.strip()
    return int(text) if text else None


def selected_setup_preset_id(
    session: MutableMapping[str, Any],
    setup_options: GameSetupOptionsResponse,
) -> str | None:
    """Return the selected setup preset id."""
    preset_ids = {preset.id for preset in setup_options.setup_presets}
    draft_value = game_setup_draft(session).setup_preset_id
    if draft_value in preset_ids:
        return draft_value
    if setup_options.default_setup_preset_id in preset_ids:
        return setup_options.default_setup_preset_id
    return setup_options.setup_presets[0].id if setup_options.setup_presets else None


def remember_setup_preset_id(session: MutableMapping[str, Any], value: str | None) -> None:
    """Store the selected setup preset id."""
    draft = game_setup_draft(session).model_copy(update={"setup_preset_id": value})
    remember_game_setup_draft(session, draft)


def selected_scenario_id(
    session: MutableMapping[str, Any],
    setup_options: GameSetupOptionsResponse,
) -> str | None:
    """Return the selected scenario id."""
    scenario_ids = {scenario.id for scenario in setup_options.scenarios}
    draft_value = game_setup_draft(session).scenario_id
    if draft_value in scenario_ids:
        return draft_value
    preset_id = selected_setup_preset_id(session, setup_options)
    preset = _setup_preset_by_id(setup_options, preset_id)
    if preset is not None and preset.scenario_id in scenario_ids:
        return preset.scenario_id
    if setup_options.default_scenario_id in scenario_ids:
        return setup_options.default_scenario_id
    return setup_options.scenarios[0].id if setup_options.scenarios else None


def remember_scenario_id(session: MutableMapping[str, Any], value: str | None) -> None:
    """Store the selected scenario id."""
    draft = game_setup_draft(session).model_copy(update={"scenario_id": value})
    remember_game_setup_draft(session, draft)


def narration_mode(
    session: MutableMapping[str, Any], setup_options: GameSetupOptionsResponse
) -> NarrationMode:
    """Return the selected public narration mode."""
    draft_value = game_setup_draft(session).narration_mode
    if draft_value in NARRATION_MODES:
        return draft_value
    return setup_options.default_narration_mode


def remember_narration_mode(session: MutableMapping[str, Any], value: NarrationMode) -> None:
    """Store the selected public narration mode."""
    draft = game_setup_draft(session).model_copy(update={"narration_mode": value})
    remember_game_setup_draft(session, draft)


def selected_manual_player_id(
    session: MutableMapping[str, Any],
    counts: Mapping[str, int],
    *,
    default_player_id: str,
) -> str | None:
    """Return the selected playable manual seat."""
    valid_player_ids = {player_id for player_id, _ in seat_options(counts)}
    if not valid_player_ids:
        return None
    draft_value = game_setup_draft(session).manual_player_id
    if draft_value in valid_player_ids:
        return draft_value
    if default_player_id in valid_player_ids:
        return default_player_id
    return seat_options(counts)[0][0]


def remember_manual_player_id(session: MutableMapping[str, Any], value: str | None) -> None:
    """Store the selected playable manual seat."""
    draft = game_setup_draft(session).model_copy(update={"manual_player_id": value})
    remember_game_setup_draft(session, draft)


def character_assignments(
    session: MutableMapping[str, Any],
    setup_options: GameSetupOptionsResponse,
    *,
    player_count: int,
) -> dict[str, str]:
    """Return selected character ids keyed by generated player id."""
    assignments = game_setup_draft(session).character_assignments
    valid_players = generated_player_ids(player_count)
    valid_characters = {character.id for character in setup_options.characters}
    return {
        player_id: character_id
        for player_id, character_id in assignments.items()
        if player_id in valid_players and character_id in valid_characters
    }


def remember_character_assignment(
    session: MutableMapping[str, Any],
    *,
    player_id: str,
    character_id: str | None,
) -> None:
    """Store one generated seat to character selection."""
    draft = game_setup_draft(session)
    assignments = dict(draft.character_assignments)
    if character_id is None:
        assignments.pop(player_id, None)
    else:
        assignments[player_id] = character_id
    remember_game_setup_draft(
        session,
        draft.model_copy(update={"character_assignments": assignments}),
    )


def custom_roles(session: MutableMapping[str, Any]) -> list[CustomRoleDefinitionRequest]:
    """Return valid session-scoped custom role definitions."""
    raw_items = session.get(KEY_CUSTOM_ROLE_DEFINITIONS)
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
    raw_items = session.get(KEY_CUSTOM_CHARACTER_DEFINITIONS)
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
    identity_faction: str,
    victory_team: str,
    objective: str,
    abilities: list[str],
    difficulty: int,
) -> None:
    """Append one custom role definition to the current session."""
    definition = CustomRoleDefinitionRequest(
        id=f"custom_role_{uuid4().hex[:10]}",
        name=name,
        identity_faction=cast(Any, identity_faction),
        victory_team=cast(Any, victory_team),
        objective=objective,
        abilities=abilities,
        description=_custom_role_description(identity_faction, abilities),
        difficulty=difficulty,
    )
    session[KEY_CUSTOM_ROLE_DEFINITIONS] = [
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
    session[KEY_CUSTOM_CHARACTER_DEFINITIONS] = [
        item.model_dump(mode="json") for item in [*custom_characters(session), definition]
    ]


def clear_custom_definitions(session: MutableMapping[str, Any]) -> None:
    """Remove all session-scoped custom definitions."""
    session.pop(KEY_CUSTOM_ROLE_DEFINITIONS, None)
    session.pop(KEY_CUSTOM_CHARACTER_DEFINITIONS, None)
    draft = game_setup_draft(session).model_copy(update={"character_assignments": {}})
    remember_game_setup_draft(session, draft)


def preset_counts(preset: str, setup_options: GameSetupOptionsResponse) -> dict[str, int]:
    """Return role counts for a named preset."""
    preset_definition = _setup_preset_by_id(setup_options, preset)
    if preset_definition is not None:
        return _counts_for_roles(preset_definition.role_counts, setup_options.roles)
    return dict(setup_options.default_role_counts)


def validate_setup(
    counts: Mapping[str, int],
    setup_options: GameSetupOptionsResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> SetupValidation:
    """Validate role counts for the setup screen."""
    messages: list[str] = []
    total = sum(counts.values())
    min_players = setup_options.player_count["min"]
    max_players = setup_options.player_count["max"]
    if total < min_players or total > max_players:
        messages.append(catalog.t(lang, "setup.validation.total", min=min_players, max=max_players))

    known_role_ids = {role.id for role in setup_options.roles}
    unknown_roles = sorted(set(counts) - known_role_ids)
    if unknown_roles:
        messages.append(
            catalog.t(lang, "setup.validation.unknown_roles", roles=", ".join(unknown_roles))
        )

    if any(count < 0 for count in counts.values()):
        messages.append(catalog.t(lang, "setup.validation.negative"))

    faction_totals = {"village": 0, "werewolf": 0}
    for role in setup_options.roles:
        if role.identity_faction in faction_totals:
            faction_totals[role.identity_faction] += counts.get(role.id, 0)
    for faction, count in faction_totals.items():
        if count < 1:
            messages.append(catalog.t(lang, f"setup.validation.faction.{faction}"))

    return SetupValidation(messages=messages)


def seat_options(counts: Mapping[str, int]) -> list[tuple[str, str]]:
    """Return generated manual seat options."""
    total = sum(counts.values())
    return [
        (
            player_id := generated_player_id(index),
            public_generated_player_label(player_id) or player_id,
        )
        for index in range(1, total + 1)
    ]


def setup_summary(
    counts: Mapping[str, int],
    *,
    rules: LocalRulesSettings,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    """Return a compact setup summary."""
    role_parts = [
        f"{_role_name(role_id, setup_options, catalog, lang)} {count}"
        for role_id, count in counts.items()
        if count > 0
    ]
    tie_rule = catalog.t(
        lang,
        "setup.summary.tie.no_elimination"
        if rules.vote_tie_resolution == "no_elimination"
        else "setup.summary.tie.random_elimination"
        if rules.vote_tie_resolution == "random_elimination"
        else "setup.summary.tie.revote",
    )
    first_night = catalog.t(
        lang,
        "setup.summary.first_night.on"
        if rules.enable_first_night_attack
        else "setup.summary.first_night.off",
    )
    speech_limit = catalog.t(
        lang,
        "setup.summary.speech_limit",
        count=rules.day_speech_limit_per_player,
    )
    return catalog.t(
        lang,
        "setup.summary",
        players=sum(counts.values()),
        roles=", ".join(role_parts),
        first_night=first_night,
        tie_rule=tie_rule,
        speech_limit=speech_limit,
    )


def _counts_for_roles(counts: Mapping[str, int], roles: list[RoleDefinitionView]) -> dict[str, int]:
    return {role.id: max(0, int(counts.get(role.id, 0))) for role in roles}


def _role_name(
    role_id: str,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    for role in setup_options.roles:
        if role.id == role_id:
            return role.name
    return catalog.label(lang, "role", role_id)


def _setup_preset_by_id(
    setup_options: GameSetupOptionsResponse,
    preset_id: str | None,
) -> SetupPresetDefinitionView | None:
    if preset_id is None:
        return None
    for preset in setup_options.setup_presets:
        if preset.id == preset_id:
            return preset
    return None


def _custom_role_description(faction: str, abilities: list[str]) -> str:
    ability_text = ", ".join(abilities) if abilities else CUSTOM_ROLE_NO_ABILITIES_TEXT
    return f"faction={faction}; abilities={ability_text}"
