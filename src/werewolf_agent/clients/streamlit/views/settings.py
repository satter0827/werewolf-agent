"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
from typing import Any, cast

from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    load_setup_options,
)
from werewolf_agent.clients.streamlit.preferences import remember_language
from werewolf_agent.clients.streamlit.setup import (
    KEY_ROLE_COUNT_WIDGET_PREFIX,
    NARRATION_MODES,
    add_custom_character,
    add_custom_role,
    character_assignments,
    clear_custom_definitions,
    narration_mode,
    preset_counts,
    remember_character_assignment,
    remember_narration_mode,
    remember_role_counts,
    remember_rules,
    remember_scenario_id,
    remember_setup_preset_id,
    role_counts,
    rules,
    seat_options,
    selected_scenario_id,
    selected_setup_preset_id,
    setup_options_with_session_customs,
)
from werewolf_agent.contracts import (
    AppError,
)
from werewolf_agent.contracts.schemas import (
    CharacterDefinitionView,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    NarrationMode,
)
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


def _render_settings_screen(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render Streamlit-wide preferences and definition management."""
    st.title(catalog.t(lang, "settings.title"))
    st.caption(catalog.t(lang, "settings.caption"))
    tab_ids = ("preferences", "role_definitions", "character_definitions")
    tabs = st.tabs(
        [catalog.t(lang, f"settings.tab.{tab_id}") for tab_id in tab_ids],
        key="settings_tabs",
    )
    setup_options: GameSetupOptionsResponse | None = None
    setup_error: AppError | None = None
    try:
        setup_options = setup_options_with_session_customs(
            st.session_state,
            load_setup_options(settings=settings),
        )
    except AppError as exc:
        setup_error = exc

    for tab_id, tab in zip(tab_ids, tabs, strict=True):
        with tab:
            if tab_id == "preferences":
                _render_common_settings(st, settings=settings, catalog=catalog, lang=lang)
            elif setup_error is not None:
                st.error(setup_error.detail)
            elif tab_id == "role_definitions" and setup_options is not None:
                _render_role_definition_settings(
                    st,
                    setup_options=setup_options,
                    catalog=catalog,
                    lang=lang,
                )
            elif setup_options is not None:
                _render_character_definition_settings(
                    st,
                    setup_options=setup_options,
                    catalog=catalog,
                    lang=lang,
                )


def _render_common_settings(
    st: Any,
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render preferences shared by every game screen."""
    language_codes = list(catalog.languages)
    selected_language = st.selectbox(
        catalog.t(lang, "settings.language"),
        language_codes,
        index=language_codes.index(lang) if lang in language_codes else 0,
        format_func=lambda value: catalog.languages[value],
    )
    if selected_language != lang:
        remember_language(st.session_state, str(selected_language))
        st.rerun()

    if st.button(catalog.t(lang, "settings.clear_custom"), use_container_width=True):
        clear_custom_definitions(st.session_state)
        st.success(catalog.t(lang, "settings.saved"))
        st.rerun()


def _render_scenario_settings(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    if not setup_options.scenarios:
        st.caption(catalog.t(lang, "common.none"))
        return
    current_id = selected_scenario_id(st.session_state, setup_options)
    selected = st.selectbox(
        catalog.t(lang, "settings.scenario"),
        setup_options.scenarios,
        index=_scenario_index(setup_options, current_id),
        format_func=lambda value: value.name,
    )
    remember_scenario_id(st.session_state, selected.id)
    st.info(selected.summary)


def _render_narration_setup(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render the game narration selector."""
    modes = list(NARRATION_MODES)
    current_mode = narration_mode(st.session_state, setup_options)
    selected_mode = st.selectbox(
        catalog.t(lang, "settings.narration"),
        modes,
        index=modes.index(current_mode) if current_mode in modes else 0,
        format_func=lambda value: _narration_label(value, catalog, lang),
    )
    remember_narration_mode(st.session_state, cast(NarrationMode, selected_mode))


def _render_setup_preset_selector(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render the game setup preset selector."""
    if not setup_options.setup_presets:
        return
    current_preset_id = selected_setup_preset_id(st.session_state, setup_options)
    selected_preset = st.selectbox(
        catalog.t(lang, "setup.preset"),
        setup_options.setup_presets,
        index=_setup_preset_index(setup_options, current_preset_id),
        format_func=lambda value: value.name,
    )
    if selected_preset.id != current_preset_id:
        counts = preset_counts(selected_preset.id, setup_options)
        remember_setup_preset_id(st.session_state, selected_preset.id)
        remember_scenario_id(st.session_state, selected_preset.scenario_id)
        remember_role_counts(st.session_state, counts)
        for role_id, count in counts.items():
            st.session_state[_role_count_key(role_id)] = count
        st.rerun()


def _render_role_definition_settings(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render shared role definitions and custom role management."""
    st.header(catalog.t(lang, "settings.role_catalog"))
    for role in setup_options.roles:
        abilities = [
            _ability_name(setup_options, ability_id, catalog, lang) for ability_id in role.abilities
        ]
        ability_text = ", ".join(abilities) if abilities else catalog.t(lang, "common.none")
        st.markdown(
            f"**{role.name}** / "
            f"{catalog.label(lang, 'faction', role.identity_faction)} / {ability_text}"
        )
    _render_custom_role_form(st, setup_options=setup_options, catalog=catalog, lang=lang)


def _render_character_assignments(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render game character assignments for generated seats."""
    counts = role_counts(st.session_state, setup_options)
    total_players = sum(counts.values())
    current_assignments = character_assignments(
        st.session_state,
        setup_options,
        player_count=total_players,
    )
    st.header(catalog.t(lang, "settings.character_assignments"))
    character_options: list[CharacterDefinitionView | None] = [None, *setup_options.characters]
    for player_id, seat_label in seat_options(counts):
        current_character_id = current_assignments.get(player_id)
        selected = st.selectbox(
            seat_label,
            character_options,
            index=_character_option_index(character_options, current_character_id),
            key=f"character_assignment:{player_id}",
            format_func=lambda value: catalog.t(lang, "settings.character.auto")
            if value is None
            else _character_label(value),
        )
        remember_character_assignment(
            st.session_state,
            player_id=player_id,
            character_id=None if selected is None else selected.id,
        )
    refreshed_assignments = character_assignments(
        st.session_state,
        setup_options,
        player_count=total_players,
    )
    if _has_duplicate_values(refreshed_assignments):
        st.warning(catalog.t(lang, "settings.character.duplicate"))


def _render_character_definition_settings(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render shared character definitions and custom character management."""
    st.header(catalog.t(lang, "settings.character_catalog"))
    for character in setup_options.characters:
        st.markdown(f"**{character.name}** / {character.age} / {character.gender}")
    _render_custom_character_form(st, setup_options=setup_options, catalog=catalog, lang=lang)


def _render_custom_role_form(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    with st.form("streamlit-custom-role"):
        name = st.text_input(
            catalog.t(lang, "settings.custom_role.name"),
            value=catalog.t(lang, "settings.custom_role.default_name"),
        )
        faction_ids = sorted({role.identity_faction for role in setup_options.roles})
        identity_faction = st.radio(
            catalog.t(lang, "settings.custom_role.faction"),
            faction_ids,
            format_func=lambda value: catalog.label(lang, "faction", value),
            horizontal=True,
        )
        victory_team = st.radio(
            catalog.t(lang, "settings.custom_role.victory_team"),
            faction_ids,
            format_func=lambda value: catalog.label(lang, "faction", value),
            horizontal=True,
        )
        objective = st.text_area(
            catalog.t(lang, "settings.custom_role.objective"),
            value=catalog.t(lang, "settings.custom_role.default_objective"),
        )
        abilities = st.multiselect(
            catalog.t(lang, "settings.custom_role.abilities"),
            [ability.id for ability in setup_options.abilities],
            format_func=lambda value: _ability_name(setup_options, str(value), catalog, lang),
        )
        difficulty = st.slider(
            catalog.t(lang, "settings.custom_role.difficulty"),
            min_value=1,
            max_value=5,
            value=2,
        )
        submitted = st.form_submit_button(catalog.t(lang, "settings.custom_role.add"))
    if submitted:
        add_custom_role(
            st.session_state,
            name=str(name),
            identity_faction=str(identity_faction),
            victory_team=str(victory_team),
            objective=str(objective),
            abilities=[str(ability) for ability in abilities],
            difficulty=int(difficulty),
        )
        st.success(catalog.t(lang, "settings.saved"))
        st.rerun()


def _render_custom_character_form(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    with st.form("streamlit-custom-character"):
        name = st.selectbox(
            catalog.t(lang, "settings.custom_character.name"),
            _message_options(catalog, lang, "settings.character.name", 6),
        )
        age = st.number_input(
            catalog.t(lang, "settings.custom_character.age"),
            min_value=18,
            max_value=99,
            value=30,
            step=1,
        )
        gender = st.selectbox(
            catalog.t(lang, "settings.custom_character.gender"),
            _message_options(catalog, lang, "settings.character.gender", 4),
        )
        personality = st.selectbox(
            catalog.t(lang, "settings.custom_character.personality"),
            _message_options(catalog, lang, "settings.character.personality", 4),
        )
        speaking_style = st.selectbox(
            catalog.t(lang, "settings.custom_character.speaking"),
            _message_options(catalog, lang, "settings.character.speaking", 4),
        )
        reasoning_style = st.selectbox(
            catalog.t(lang, "settings.custom_character.reasoning"),
            _message_options(catalog, lang, "settings.character.reasoning", 4),
        )
        risk_tolerance = st.selectbox(
            catalog.t(lang, "settings.custom_character.risk"),
            ["low", "medium", "high"],
            format_func=lambda value: catalog.label(lang, "risk", value),
        )
        submitted = st.form_submit_button(catalog.t(lang, "settings.custom_character.add"))
    if submitted:
        existing_names = {character.name for character in setup_options.characters}
        if str(name) in existing_names:
            st.warning(catalog.t(lang, "settings.character.name_duplicate"))
            return
        add_custom_character(
            st.session_state,
            name=str(name),
            age=int(age),
            gender=str(gender),
            personality=str(personality),
            speaking_style=str(speaking_style),
            reasoning_style=str(reasoning_style),
            risk_tolerance=str(risk_tolerance),
        )
        st.success(catalog.t(lang, "settings.saved"))
        st.rerun()


def _render_local_rules_settings(
    st: Any,
    *,
    setup_options: GameSetupOptionsResponse,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render local rules for the next game."""
    current_rules = rules(st.session_state, setup_options)
    st.header(catalog.t(lang, "settings.local_rules"))
    day_speech_limit_per_player = st.number_input(
        catalog.t(lang, "settings.rule.day_speech_limit_per_player"),
        min_value=1,
        max_value=10,
        step=1,
        value=current_rules.day_speech_limit_per_player,
    )
    allow_self_vote = st.checkbox(
        catalog.t(lang, "settings.rule.allow_self_vote"),
        value=current_rules.allow_self_vote,
    )
    allow_vote_revision = st.checkbox(
        catalog.t(lang, "settings.rule.allow_vote_revision"),
        value=current_rules.allow_vote_revision,
    )
    allow_night_action_revision = st.checkbox(
        catalog.t(lang, "settings.rule.allow_night_action_revision"),
        value=current_rules.allow_night_action_revision,
    )
    enable_first_night_attack = st.checkbox(
        catalog.t(lang, "settings.rule.enable_first_night_attack"),
        value=current_rules.enable_first_night_attack,
    )
    allow_knight_self_guard = st.checkbox(
        catalog.t(lang, "settings.rule.allow_knight_self_guard"),
        value=current_rules.allow_knight_self_guard,
    )
    allow_knight_repeat_guard = st.checkbox(
        catalog.t(lang, "settings.rule.allow_knight_repeat_guard"),
        value=current_rules.allow_knight_repeat_guard,
    )
    allow_seer_self_inspect = st.checkbox(
        catalog.t(lang, "settings.rule.allow_seer_self_inspect"),
        value=current_rules.allow_seer_self_inspect,
    )
    allow_werewolf_friendly_fire = st.checkbox(
        catalog.t(lang, "settings.rule.allow_werewolf_friendly_fire"),
        value=current_rules.allow_werewolf_friendly_fire,
    )
    reveal_role_on_death = st.checkbox(
        catalog.t(lang, "settings.rule.reveal_role_on_death"),
        value=current_rules.reveal_role_on_death,
    )
    tie_rule = st.radio(
        catalog.t(lang, "settings.rule.tie"),
        ["no_elimination", "random_elimination", "revote"],
        index=["no_elimination", "random_elimination", "revote"].index(
            current_rules.vote_tie_resolution
        ),
        format_func=lambda value: catalog.t(
            lang,
            "settings.rule.tie.no_elimination"
            if value == "no_elimination"
            else "settings.rule.tie.random_elimination"
            if value == "random_elimination"
            else "settings.rule.tie.revote",
        ),
    )
    wolf_attack_tie_resolution = st.selectbox(
        catalog.t(lang, "settings.rule.wolf_attack_tie_resolution"),
        ["random_target", "no_attack"],
        index=["random_target", "no_attack"].index(current_rules.wolf_attack_tie_resolution),
        format_func=lambda value: catalog.t(
            lang, f"settings.rule.wolf_attack_tie_resolution.{value}"
        ),
    )
    seer_result_detail = st.selectbox(
        catalog.t(lang, "settings.rule.seer_result_detail"),
        ["faction", "role"],
        index=["faction", "role"].index(current_rules.seer_result_detail),
        format_func=lambda value: catalog.t(lang, f"settings.rule.result_detail.{value}"),
    )
    medium_result_detail = st.selectbox(
        catalog.t(lang, "settings.rule.medium_result_detail"),
        ["faction", "role"],
        index=["faction", "role"].index(current_rules.medium_result_detail),
        format_func=lambda value: catalog.t(lang, f"settings.rule.result_detail.{value}"),
    )
    starting_phase = st.selectbox(
        catalog.t(lang, "settings.rule.starting_phase"),
        ["night", "day_discussion"],
        index=["night", "day_discussion"].index(current_rules.starting_phase),
        format_func=lambda value: catalog.t(lang, f"settings.rule.starting_phase.{value}"),
    )
    next_rules = LocalRulesSettings(
        day_speech_limit_per_player=int(day_speech_limit_per_player),
        allow_self_vote=allow_self_vote,
        allow_vote_revision=allow_vote_revision,
        allow_night_action_revision=allow_night_action_revision,
        enable_first_night_attack=enable_first_night_attack,
        vote_tie_resolution=tie_rule,
        wolf_attack_tie_resolution=wolf_attack_tie_resolution,
        seer_result_detail=seer_result_detail,
        medium_result_detail=medium_result_detail,
        starting_phase=starting_phase,
        allow_knight_self_guard=allow_knight_self_guard,
        allow_knight_repeat_guard=allow_knight_repeat_guard,
        allow_seer_self_inspect=allow_seer_self_inspect,
        allow_werewolf_friendly_fire=allow_werewolf_friendly_fire,
        reveal_role_on_death=reveal_role_on_death,
        require_all_actions_before_advance=current_rules.require_all_actions_before_advance,
    )
    if next_rules != current_rules:
        remember_rules(st.session_state, next_rules)
    reset_clicked = st.button(
        catalog.t(lang, "common.default"),
        use_container_width=True,
    )
    if reset_clicked:
        remember_rules(st.session_state, setup_options.default_rules)
        st.success(catalog.t(lang, "settings.reset"))
        st.rerun()


def _scenario_index(setup_options: GameSetupOptionsResponse, scenario_id: str | None) -> int:
    for index, scenario in enumerate(setup_options.scenarios):
        if scenario.id == scenario_id:
            return index
    return 0


def _setup_preset_index(setup_options: GameSetupOptionsResponse, preset_id: str | None) -> int:
    for index, preset in enumerate(setup_options.setup_presets):
        if preset.id == preset_id:
            return index
    return 0


def _character_option_index(
    options: list[CharacterDefinitionView | None],
    character_id: str | None,
) -> int:
    for index, option in enumerate(options):
        if option is not None and option.id == character_id:
            return index
    return 0


def _seat_index(seats: list[tuple[str, str]], player_id: str | None) -> int:
    """Return the selected seat index for Streamlit selectbox defaults."""
    for index, seat in enumerate(seats):
        if seat[0] == player_id:
            return index
    return 0


def _scenario_name(
    setup_options: GameSetupOptionsResponse,
    scenario_id: str | None,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    for scenario in setup_options.scenarios:
        if scenario.id == scenario_id:
            return scenario.name
    return catalog.t(lang, "common.none")


def _setup_preset_name(
    setup_options: GameSetupOptionsResponse,
    preset_id: str,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    for preset in setup_options.setup_presets:
        if preset.id == preset_id:
            return preset.name
    return catalog.t(lang, "common.none")


def _narration_label(value: NarrationMode, catalog: I18nCatalog, lang: Language) -> str:
    return catalog.label(lang, "narration", value)


def _ability_name(
    setup_options: GameSetupOptionsResponse,
    ability_id: str,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    for ability in setup_options.abilities:
        if ability.id == ability_id:
            return ability.name
    return catalog.label(lang, "action", ability_id)


def _character_label(character: CharacterDefinitionView) -> str:
    return f"{character.name} / {character.age} / {character.gender}"


def _message_options(
    catalog: I18nCatalog,
    lang: Language,
    prefix: str,
    count: int,
) -> list[str]:
    """Return localized form choices from the translation catalog."""
    return [catalog.t(lang, f"{prefix}.{index}") for index in range(1, count + 1)]


def _has_duplicate_values(values: dict[str, str]) -> bool:
    non_empty_values = [value for value in values.values() if value]
    return len(set(non_empty_values)) != len(non_empty_values)


def _role_count_key(role_id: str) -> str:
    return f"{KEY_ROLE_COUNT_WIDGET_PREFIX}:{role_id}"
