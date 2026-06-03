"""Playable Streamlit entry point for one manual player."""

from __future__ import annotations

import importlib
import secrets
import time
from typing import Any, cast
from uuid import uuid4

from werewolf_agent.commons.shared.constants import DEFAULT_NARRATION_MODE
from werewolf_agent.contracts import (
    ACTIVE_ADVANCE_JOB_STATUSES,
    ADVANCE_JOB_STATUS_FAILED,
    AppError,
)
from werewolf_agent.contracts.schemas import (
    CharacterDefinitionView,
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    GameSetupOptionsResponse,
    LocalRulesSettings,
    NarrationMode,
)
from werewolf_agent.interface.entrypoint.streamlit.components import (
    action_header_html,
    advance_note_html,
    auto_progress_html,
    command_divider_html,
    game_table_html,
    hand_panel_html,
    observation_memo_html,
    observation_panel_html,
    observer_log_html,
    status_grid_html,
    timeline_section_html,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import (
    I18nCatalog,
    Language,
    load_i18n,
)
from werewolf_agent.interface.entrypoint.streamlit.operations import (
    create_game_from_setup,
    list_recent_games,
    load_advance_job,
    load_game_screen,
    load_setup_options,
    log_streamlit_rerun_started,
    start_advance_step,
    submit_screen_action,
)
from werewolf_agent.interface.entrypoint.streamlit.saves import (
    build_saved_game_options,
    create_save_slot,
    load_save_slots,
    upsert_save_slot,
)
from werewolf_agent.interface.entrypoint.streamlit.setup import (
    KEY_ROLE_COUNT_WIDGET_PREFIX,
    NARRATION_MODES,
    VIEW_APP_SETTINGS,
    VIEW_GAME,
    VIEW_OBSERVE_SETUP,
    VIEW_PLAY_SETUP,
    add_custom_character,
    add_custom_role,
    character_assignments,
    clear_custom_definitions,
    current_view,
    custom_characters,
    custom_roles,
    narration_mode,
    preferred_api_url,
    preferred_language,
    preset_counts,
    remember_character_assignment,
    remember_manual_player_id,
    remember_narration_mode,
    remember_preferred_api_url,
    remember_preferred_language,
    remember_role_counts,
    remember_rules,
    remember_scenario_id,
    remember_seed_text,
    remember_setup_preset_id,
    role_counts,
    rules,
    seat_options,
    seed_from_text,
    seed_text,
    selected_manual_player_id,
    selected_scenario_id,
    selected_setup_preset_id,
    setup_options_with_session_customs,
    setup_summary,
    switch_view,
    validate_setup,
)
from werewolf_agent.interface.entrypoint.streamlit.state import (
    KEY_MESSAGE,
    KEY_SELECTED_SAVE_ID,
    advance_job_id,
    auto_advance_state,
    clear_advance_job,
    clear_message,
    consume_auto_advance_notice,
    manual_player_tokens_by_slot,
    pause_auto_advance,
    record_auto_advance_step,
    remember_advance_job,
    remember_manual_player_token,
    remember_selected_save,
    start_auto_advance,
    sync_auto_advance_game,
    text_value,
)
from werewolf_agent.interface.entrypoint.streamlit.styles import STREAMLIT_CSS
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    ActionChoiceView,
    GameScreenView,
    SavedGameOptionView,
)
from werewolf_agent.interface.runtime import (
    AppSettings,
    bind_observation_context,
    configure_interface_logging,
    get_settings,
)


def main() -> None:
    """Render the Streamlit application."""
    st = _streamlit()
    settings = get_settings()
    configure_interface_logging(settings, service_name=settings.streamlit_service_name)
    with bind_observation_context(trace_id=str(uuid4())):
        log_streamlit_rerun_started(settings)
        _render_app(st, settings)


def _render_app(st: Any, settings: AppSettings) -> None:
    """Render one Streamlit rerun with a bound observation context."""
    catalog = load_i18n(settings)
    lang = preferred_language(st.session_state, settings.streamlit_language)
    st.set_page_config(
        page_title=settings.streamlit_page_title,
        page_icon="🐺",
        layout="wide",
        initial_sidebar_state=settings.streamlit_initial_sidebar_state,
    )
    st.markdown(STREAMLIT_CSS, unsafe_allow_html=True)

    api_url, selected_option, view = _render_sidebar(st, settings, catalog=catalog, lang=lang)
    if view == VIEW_APP_SETTINGS:
        _render_settings_screen(st, settings=settings, api_url=api_url, catalog=catalog, lang=lang)
        return
    if view != VIEW_GAME or selected_option is None:
        _render_setup_screen(
            st,
            settings=settings,
            api_url=api_url,
            catalog=catalog,
            lang=lang,
            observer=view == VIEW_OBSERVE_SETUP,
        )
        return

    sync_auto_advance_game(st.session_state, selected_option.game_id)
    try:
        screen = load_game_screen(
            api_url=api_url,
            settings=settings,
            game_id=selected_option.game_id,
            manual_player_id=selected_option.manual_player_id,
            manual_token=selected_option.manual_token,
            screen_mode=selected_option.mode,
            catalog=catalog,
            lang=lang,
        )
    except AppError as exc:
        st.error(exc.detail)
        return
    if selected_option.mode != "playable" or screen.can_submit_action or screen.is_completed:
        pause_auto_advance(st.session_state)

    _render_status_bar(st, screen)
    table_column, hand_column = st.columns([1.55, 1], gap="medium")
    with table_column:
        _render_game_table(st, screen, catalog=catalog, lang=lang)
        _render_timeline(st, screen, variant="desktop", catalog=catalog, lang=lang)
        _render_next_actions(
            st,
            settings=settings,
            api_url=api_url,
            screen=screen,
            selected_option=selected_option,
            catalog=catalog,
            lang=lang,
        )
    with hand_column:
        _render_action_panel(
            st,
            settings=settings,
            api_url=api_url,
            screen=screen,
            selected_option=selected_option,
            catalog=catalog,
            lang=lang,
        )
    _render_timeline(st, screen, variant="mobile", catalog=catalog, lang=lang)


def _render_sidebar(
    st: Any,
    settings: AppSettings,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> tuple[str, SavedGameOptionView | None, str]:
    _render_sidebar_brand(st, catalog=catalog, lang=lang)
    api_url = preferred_api_url(st.session_state, settings.streamlit_resolved_api_url)

    st.sidebar.divider()
    st.sidebar.subheader(catalog.t(lang, "sidebar.saves"))
    selected_option = _render_save_selector(
        st,
        settings=settings,
        api_url=api_url,
        catalog=catalog,
        lang=lang,
    )

    st.sidebar.divider()
    st.sidebar.subheader(catalog.t(lang, "sidebar.navigation"))
    if st.sidebar.button(f"▶ {catalog.t(lang, 'nav.play')}", use_container_width=True):
        switch_view(st.session_state, VIEW_PLAY_SETUP)
        st.rerun()
    if st.sidebar.button(f"◉ {catalog.t(lang, 'nav.observe')}", use_container_width=True):
        switch_view(st.session_state, VIEW_OBSERVE_SETUP)
        st.rerun()
    if st.sidebar.button(f"⚙ {catalog.t(lang, 'nav.settings')}", use_container_width=True):
        switch_view(st.session_state, VIEW_APP_SETTINGS)
        st.rerun()
    return api_url, selected_option, current_view(st.session_state)


def _render_sidebar_brand(st: Any, *, catalog: I18nCatalog, lang: Language) -> None:
    st.sidebar.markdown(
        f"""
        <div class="wa-sidebar-brand">
                <div class="wa-brand-mark">🐺</div>
                <div>
                    <div class="wa-brand-title">Werewolf Agent</div>
                    <div class="wa-brand-mode">{catalog.t(lang, "brand.mode")}</div>
                </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_save_selector(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    catalog: I18nCatalog,
    lang: Language,
) -> SavedGameOptionView | None:
    slots = load_save_slots(settings.streamlit_save_file_path)
    try:
        games = list_recent_games(api_url=api_url, settings=settings)
    except AppError:
        games = []
        st.sidebar.caption(catalog.t(lang, "save.unavailable"))
    options = build_saved_game_options(
        slots,
        games,
        catalog=catalog,
        lang=lang,
        manual_player_tokens=manual_player_tokens_by_slot(st.session_state),
    )
    if not options:
        st.sidebar.caption(catalog.t(lang, "save.empty"))
        return None

    selected_id = text_value(st.session_state, KEY_SELECTED_SAVE_ID)
    index = _selected_option_index(options, selected_id)
    selected_option = st.sidebar.selectbox(
        catalog.t(lang, "save.selector"),
        options,
        index=index,
        format_func=lambda option: option.label,
    )
    selected_option = cast(SavedGameOptionView, selected_option)
    if st.sidebar.button(catalog.t(lang, "save.open"), use_container_width=True):
        remember_selected_save(st.session_state, selected_option.option_id)
        switch_view(st.session_state, VIEW_GAME)
        st.rerun()
    if current_view(st.session_state) != VIEW_GAME:
        return None
    return _selected_option_by_id(options, text_value(st.session_state, KEY_SELECTED_SAVE_ID))


def _render_setup_screen(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    catalog: I18nCatalog,
    lang: Language,
    observer: bool,
) -> None:
    try:
        setup_options = setup_options_with_session_customs(
            st.session_state,
            load_setup_options(api_url=api_url, settings=settings),
        )
    except AppError as exc:
        st.error(exc.detail)
        return

    st.header(catalog.t(lang, "setup.title.observe" if observer else "setup.title.play"))
    st.caption(catalog.t(lang, "setup.mode.observe" if observer else "setup.mode.play"))

    _render_setup_preset_selector(st, setup_options=setup_options, catalog=catalog, lang=lang)
    _render_scenario_settings(st, setup_options=setup_options, catalog=catalog, lang=lang)
    _render_narration_setup(st, setup_options=setup_options, catalog=catalog, lang=lang)
    seed_value = _render_seed_controls(st, settings, catalog, lang)
    counts = _render_role_counts(st, setup_options, catalog=catalog, lang=lang)
    _render_character_assignments(st, setup_options=setup_options, catalog=catalog, lang=lang)
    _render_local_rules_settings(st, setup_options=setup_options, catalog=catalog, lang=lang)

    counts = role_counts(st.session_state, setup_options)
    active_rules = rules(st.session_state, setup_options)
    scenario_id = selected_scenario_id(st.session_state, setup_options)
    preset_id = selected_setup_preset_id(st.session_state, setup_options)
    active_narration_mode = narration_mode(st.session_state, setup_options)
    validation = validate_setup(counts, setup_options, catalog=catalog, lang=lang)
    total_players = sum(counts.values())
    summary_columns = st.columns(3)
    summary_columns[0].metric(
        catalog.t(lang, "settings.scenario"),
        _scenario_name(setup_options, scenario_id, catalog, lang),
    )
    summary_columns[1].metric(catalog.t(lang, "setup.total_players"), f"{total_players}")
    summary_columns[2].metric(
        catalog.t(lang, "settings.narration"),
        _narration_label(active_narration_mode, catalog, lang),
    )
    if preset_id is not None:
        st.caption(_setup_preset_name(setup_options, preset_id, catalog, lang))
    for message in validation.messages:
        st.warning(message)

    manual_player_id = (
        None
        if observer
        else _render_manual_seat_selector(
            st,
            counts,
            settings=settings,
            catalog=catalog,
            lang=lang,
        )
    )
    try:
        seed_from_text(seed_value)
    except ValueError:
        st.warning(catalog.t(lang, "setup.seed_warning"))
    st.caption(
        setup_summary(
            counts,
            rules=active_rules,
            setup_options=setup_options,
            catalog=catalog,
            lang=lang,
        )
    )

    active_assignments = character_assignments(
        st.session_state,
        setup_options,
        player_count=total_players,
    )
    disabled = (
        not validation.is_valid
        or (manual_player_id is None and not observer)
        or _has_duplicate_values(active_assignments)
    )
    if st.button(
        catalog.t(lang, "action.create_observer" if observer else "action.create_playable"),
        type="primary",
        use_container_width=True,
        disabled=disabled,
    ):
        _create_game(
            st,
            feedback=st,
            settings=settings,
            api_url=api_url,
            role_counts=counts,
            rules=active_rules,
            seed_text=seed_value,
            manual_player_id=None if observer else str(manual_player_id),
            screen_mode="observer" if observer else "playable",
            scenario_id=scenario_id,
            setup_preset_id=preset_id,
            narration_mode=active_narration_mode,
            character_assignments=active_assignments,
            custom_roles=custom_roles(st.session_state),
            custom_characters=custom_characters(st.session_state),
            catalog=catalog,
            lang=lang,
        )


def _render_role_counts(
    st: Any,
    setup_options: GameSetupOptionsResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> dict[str, int]:
    counts = role_counts(st.session_state, setup_options)
    st.subheader(catalog.t(lang, "setup.role_counts"))
    next_counts: dict[str, int] = {}
    for role in setup_options.roles:
        widget_key = _role_count_key(role.id)
        if widget_key not in st.session_state:
            st.session_state[widget_key] = int(counts.get(role.id, 0))
        ability_names = [
            _ability_name(setup_options, ability_id, catalog, lang) for ability_id in role.abilities
        ]
        next_counts[role.id] = int(
            st.number_input(
                role.name,
                min_value=0,
                max_value=setup_options.player_count["max"],
                step=1,
                key=widget_key,
                help=f"{catalog.label(lang, 'faction', role.faction)} / "
                f"{', '.join(ability_names) if ability_names else catalog.t(lang, 'common.none')}",
            )
        )
    remember_role_counts(st.session_state, next_counts)
    return next_counts


def _render_manual_seat_selector(
    st: Any,
    counts: dict[str, int],
    *,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> str | None:
    """Render the playable manual-seat selector."""
    seats = seat_options(counts)
    if not seats:
        st.warning(catalog.t(lang, "setup.no_seats"))
        return None
    current_player_id = selected_manual_player_id(
        st.session_state,
        counts,
        default_player_id=settings.streamlit_default_manual_player_id,
    )
    selected = st.selectbox(
        catalog.t(lang, "setup.seat"),
        seats,
        index=_seat_index(seats, current_player_id),
        format_func=lambda option: option[1],
    )
    remember_manual_player_id(st.session_state, selected[0])
    return str(selected[0])


def _render_seed_controls(
    st: Any,
    settings: AppSettings,
    catalog: I18nCatalog,
    lang: Language,
) -> str:
    seed = str(
        st.text_input(
            catalog.t(lang, "setup.seed"),
            value=seed_text(st.session_state, settings.streamlit_default_seed),
            help=catalog.t(lang, "setup.seed_help"),
        )
    )
    remember_seed_text(st.session_state, seed)
    first_column, second_column = st.columns(2)
    if first_column.button(catalog.t(lang, "action.random_seed"), use_container_width=True):
        remember_seed_text(st.session_state, str(secrets.randbelow(1_000_000)))
        st.rerun()
    if second_column.button(catalog.t(lang, "action.unset_seed"), use_container_width=True):
        remember_seed_text(st.session_state, "")
        st.rerun()
    try:
        seed_from_text(seed)
    except ValueError:
        st.warning(catalog.t(lang, "setup.seed_warning"))
    return seed


def _render_settings_screen(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    """Render Streamlit-wide preferences and definition management."""
    st.header(catalog.t(lang, "settings.title"))
    st.caption(catalog.t(lang, "settings.caption"))
    preferences_tab, roles_tab, characters_tab = st.tabs(
        [
            catalog.t(lang, "settings.tab.preferences"),
            catalog.t(lang, "settings.tab.role_definitions"),
            catalog.t(lang, "settings.tab.character_definitions"),
        ]
    )

    with preferences_tab:
        _render_common_settings(st, settings=settings, catalog=catalog, lang=lang)

    try:
        setup_options = setup_options_with_session_customs(
            st.session_state,
            load_setup_options(api_url=api_url, settings=settings),
        )
    except AppError as exc:
        with roles_tab:
            st.error(exc.detail)
        with characters_tab:
            st.error(exc.detail)
        return

    with roles_tab:
        _render_role_definition_settings(
            st, setup_options=setup_options, catalog=catalog, lang=lang
        )
    with characters_tab:
        _render_character_definition_settings(
            st, setup_options=setup_options, catalog=catalog, lang=lang
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
        remember_preferred_language(st.session_state, str(selected_language))
        st.rerun()

    current_api_url = preferred_api_url(st.session_state, settings.streamlit_resolved_api_url)
    selected_api_url = str(
        st.text_input(
            catalog.t(lang, "settings.api_url"),
            value=current_api_url,
        )
    )
    if selected_api_url.strip() != current_api_url:
        remember_preferred_api_url(st.session_state, selected_api_url)
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
    st.subheader(catalog.t(lang, "settings.role_catalog"))
    for role in setup_options.roles:
        abilities = [
            _ability_name(setup_options, ability_id, catalog, lang) for ability_id in role.abilities
        ]
        ability_text = ", ".join(abilities) if abilities else catalog.t(lang, "common.none")
        st.markdown(
            f"**{role.name}** / {catalog.label(lang, 'faction', role.faction)} / {ability_text}"
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
    st.subheader(catalog.t(lang, "settings.character_assignments"))
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
    st.subheader(catalog.t(lang, "settings.character_catalog"))
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
        name = st.selectbox(
            catalog.t(lang, "settings.custom_role.name"),
            _localized_options(
                lang,
                ja=["記録係", "追跡者", "沈黙の守り手", "攪乱者"],
                en=["Archivist", "Tracker", "Silent Guard", "Disruptor"],
            ),
        )
        faction = st.radio(
            catalog.t(lang, "settings.custom_role.faction"),
            ["village", "werewolf"],
            format_func=lambda value: catalog.label(lang, "faction", value),
            horizontal=True,
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
            faction=str(faction),
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
            _localized_options(
                lang,
                ja=["真央", "凛", "悠真", "詩乃", "拓海", "紬"],
                en=["Mao", "Rin", "Yuma", "Shino", "Takumi", "Tsumugi"],
            ),
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
            _localized_options(
                lang,
                ja=["指定なし", "女性", "男性", "ノンバイナリー"],
                en=["Unspecified", "Female", "Male", "Non-binary"],
            ),
        )
        personality = st.selectbox(
            catalog.t(lang, "settings.custom_character.personality"),
            _localized_options(
                lang,
                ja=["慎重", "率直", "穏やか", "好奇心旺盛"],
                en=["Careful", "Direct", "Calm", "Curious"],
            ),
        )
        speaking_style = st.selectbox(
            catalog.t(lang, "settings.custom_character.speaking"),
            _localized_options(
                lang,
                ja=["短く話す", "根拠から話す", "質問を重ねる", "柔らかく話す"],
                en=[
                    "Short statements",
                    "Evidence first",
                    "Asks questions",
                    "Soft spoken",
                ],
            ),
        )
        reasoning_style = st.selectbox(
            catalog.t(lang, "settings.custom_character.reasoning"),
            _localized_options(
                lang,
                ja=["矛盾重視", "投票重視", "発言重視", "バランス重視"],
                en=[
                    "Contradictions first",
                    "Votes first",
                    "Speech first",
                    "Balanced",
                ],
            ),
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
    st.subheader(catalog.t(lang, "settings.local_rules"))
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
        ["no_elimination", "random_elimination"],
        index=0 if current_rules.enable_no_elimination_on_tie else 1,
        format_func=lambda value: catalog.t(
            lang,
            "settings.rule.tie.no_elimination"
            if value == "no_elimination"
            else "settings.rule.tie.random_elimination",
        ),
    )
    next_rules = LocalRulesSettings(
        day_speech_limit_per_player=int(day_speech_limit_per_player),
        allow_self_vote=allow_self_vote,
        allow_vote_revision=allow_vote_revision,
        allow_night_action_revision=allow_night_action_revision,
        enable_first_night_attack=enable_first_night_attack,
        enable_no_elimination_on_tie=tie_rule == "no_elimination",
        enable_random_elimination_on_tie=tie_rule == "random_elimination",
        allow_knight_self_guard=allow_knight_self_guard,
        allow_knight_repeat_guard=allow_knight_repeat_guard,
        allow_seer_self_inspect=allow_seer_self_inspect,
        allow_werewolf_friendly_fire=allow_werewolf_friendly_fire,
        reveal_role_on_death=reveal_role_on_death,
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


def _localized_options(lang: Language, *, ja: list[str], en: list[str]) -> list[str]:
    return ja if lang == "ja" else en


def _has_duplicate_values(values: dict[str, str]) -> bool:
    non_empty_values = [value for value in values.values() if value]
    return len(set(non_empty_values)) != len(non_empty_values)


def _role_count_key(role_id: str) -> str:
    return f"{KEY_ROLE_COUNT_WIDGET_PREFIX}:{role_id}"


def _create_game(
    st: Any,
    *,
    feedback: Any,
    settings: AppSettings,
    api_url: str,
    role_counts: dict[str, int],
    rules: LocalRulesSettings,
    seed_text: str,
    manual_player_id: str | None,
    screen_mode: str,
    scenario_id: str | None = None,
    setup_preset_id: str | None = None,
    narration_mode: NarrationMode = DEFAULT_NARRATION_MODE,
    character_assignments: dict[str, str] | None = None,
    custom_roles: list[CustomRoleDefinitionRequest] | None = None,
    custom_characters: list[CustomCharacterDefinitionRequest] | None = None,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    try:
        created = create_game_from_setup(
            api_url=api_url,
            settings=settings,
            role_counts=role_counts,
            rules=rules,
            seed_text=seed_text,
            manual_player_id=manual_player_id,
            scenario_id=scenario_id,
            setup_preset_id=setup_preset_id,
            narration_mode=narration_mode,
            character_assignments=character_assignments or {},
            custom_roles=custom_roles or [],
            custom_characters=custom_characters or [],
        )
    except (AppError, ValueError) as exc:
        feedback.error(str(exc))
        return

    manual_token = (
        created.manual_player.token
        if created.manual_player is not None and created.manual_player.player_id == manual_player_id
        else ""
    )
    slot = create_save_slot(
        created,
        manual_player_id=manual_player_id,
        role_counts=role_counts,
        rules=rules,
        seed=seed_from_text(seed_text),
        scenario_id=scenario_id,
        setup_preset_id=setup_preset_id,
        narration_mode=narration_mode,
        character_assignments=character_assignments or {},
        custom_roles=custom_roles or [],
        custom_characters=custom_characters or [],
    )
    upsert_save_slot(settings.streamlit_save_file_path, slot)
    remember_manual_player_token(
        st.session_state,
        slot_id=slot.slot_id,
        manual_token=manual_token,
    )
    remember_selected_save(st.session_state, f"slot:{slot.slot_id}")
    switch_view(st.session_state, VIEW_GAME)
    clear_message(st.session_state)
    success_key = (
        "action.create_observer" if screen_mode == "observer" else "action.create_playable"
    )
    feedback.success(catalog.t(lang, success_key))
    st.rerun()


def _render_status_bar(st: Any, screen: GameScreenView) -> None:
    st.markdown(status_grid_html(screen.status_metrics), unsafe_allow_html=True)


def _render_game_table(
    st: Any,
    screen: GameScreenView,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    st.markdown(
        game_table_html(
            screen,
            title=catalog.t(lang, "game.table.title"),
            description=catalog.t(lang, "game.table.description"),
        ),
        unsafe_allow_html=True,
    )


def _render_timeline(
    st: Any,
    screen: GameScreenView,
    *,
    variant: str,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    st.markdown(
        timeline_section_html(
            screen.timeline,
            variant=variant,
            title=catalog.t(lang, "game.timeline.title"),
            description=catalog.t(lang, "game.timeline.description"),
            empty_text=catalog.t(lang, "game.timeline.empty"),
            result_summary=screen.result_summary if variant == "desktop" else None,
        ),
        unsafe_allow_html=True,
    )


def _render_next_actions(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    if not screen.is_completed:
        return
    role_counts_value = selected_option.role_counts or screen.role_counts
    rules_value = selected_option.rules or screen.rules
    if not role_counts_value or rules_value is None:
        st.caption(catalog.t(lang, "next_actions.saved_hint"))
        return

    st.divider()
    first, second, third, fourth = st.columns(4)
    if first.button(catalog.t(lang, "next_actions.random_seed"), use_container_width=True):
        _create_game(
            st,
            feedback=st,
            settings=settings,
            api_url=api_url,
            role_counts=role_counts_value,
            rules=rules_value,
            seed_text="",
            manual_player_id=selected_option.manual_player_id
            if selected_option.mode == "playable"
            else None,
            screen_mode=selected_option.mode,
            scenario_id=selected_option.scenario_id,
            setup_preset_id=selected_option.setup_preset_id,
            narration_mode=cast(NarrationMode, selected_option.narration_mode),
            character_assignments=selected_option.character_assignments or {},
            custom_roles=selected_option.custom_roles or [],
            custom_characters=selected_option.custom_characters or [],
            catalog=catalog,
            lang=lang,
        )
    seed_value = selected_option.seed if selected_option.seed is not None else screen.seed
    same_seed_text = "" if seed_value is None else str(seed_value)
    if second.button(catalog.t(lang, "next_actions.same_seed"), use_container_width=True):
        _create_game(
            st,
            feedback=st,
            settings=settings,
            api_url=api_url,
            role_counts=role_counts_value,
            rules=rules_value,
            seed_text=same_seed_text,
            manual_player_id=selected_option.manual_player_id
            if selected_option.mode == "playable"
            else None,
            screen_mode=selected_option.mode,
            scenario_id=selected_option.scenario_id,
            setup_preset_id=selected_option.setup_preset_id,
            narration_mode=cast(NarrationMode, selected_option.narration_mode),
            character_assignments=selected_option.character_assignments or {},
            custom_roles=selected_option.custom_roles or [],
            custom_characters=selected_option.custom_characters or [],
            catalog=catalog,
            lang=lang,
        )
    if third.button(catalog.t(lang, "next_actions.return_setup"), use_container_width=True):
        remember_role_counts(st.session_state, role_counts_value)
        remember_rules(st.session_state, rules_value)
        remember_seed_text(st.session_state, same_seed_text)
        remember_scenario_id(st.session_state, selected_option.scenario_id)
        remember_setup_preset_id(st.session_state, selected_option.setup_preset_id)
        remember_narration_mode(
            st.session_state,
            cast(NarrationMode, selected_option.narration_mode),
        )
        remember_manual_player_id(st.session_state, selected_option.manual_player_id)
        for player_id, character_id in (selected_option.character_assignments or {}).items():
            remember_character_assignment(
                st.session_state,
                player_id=player_id,
                character_id=character_id,
            )
        switch_view(
            st.session_state,
            VIEW_PLAY_SETUP if selected_option.mode == "playable" else VIEW_OBSERVE_SETUP,
        )
        st.rerun()
    if fourth.button(catalog.t(lang, "next_actions.saves"), use_container_width=True):
        st.info(catalog.t(lang, "next_actions.saved_hint"))


def _render_action_panel(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    with st.container(border=False, key="right_command_panel"):
        st.markdown(hand_panel_html(screen.hand_panel), unsafe_allow_html=True)
        if screen.screen_mode == "observer":
            if screen.observer_log is not None:
                st.markdown(observer_log_html(screen.observer_log), unsafe_allow_html=True)
            st.markdown(observation_memo_html(screen.observation_memo), unsafe_allow_html=True)
            return

        if screen.observation is not None:
            st.markdown(
                observation_panel_html(
                    screen.observation,
                    role_title=catalog.t(lang, "observation.role_title"),
                    info_title=catalog.t(lang, "observation.info_title"),
                    role_note_template=catalog.t(lang, "game.role_note"),
                    empty_text=catalog.t(lang, "observation.empty"),
                ),
                unsafe_allow_html=True,
            )

        if screen.is_completed:
            st.markdown(observation_memo_html(screen.observation_memo), unsafe_allow_html=True)
            return

        if advance_job_id(st.session_state, selected_option.game_id):
            _render_advance_job_progress(
                st,
                settings=settings,
                api_url=api_url,
                selected_option=selected_option,
                catalog=catalog,
                lang=lang,
            )
            st.markdown(observation_memo_html(screen.observation_memo), unsafe_allow_html=True)
            return

        if screen.can_submit_action:
            _render_action_form(
                st,
                settings=settings,
                api_url=api_url,
                screen=screen,
                selected_option=selected_option,
                catalog=catalog,
                lang=lang,
            )
            st.markdown(observation_memo_html(screen.observation_memo), unsafe_allow_html=True)
            return

        _render_auto_advance_controls(
            st,
            settings=settings,
            api_url=api_url,
            screen=screen,
            selected_option=selected_option,
            catalog=catalog,
            lang=lang,
        )
        st.markdown(observation_memo_html(screen.observation_memo), unsafe_allow_html=True)


def _render_action_form(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    manual_player_id = selected_option.manual_player_id
    if screen.observation is None or manual_player_id is None:
        return

    st.markdown(command_divider_html(), unsafe_allow_html=True)
    st.markdown(
        action_header_html(catalog.t(lang, "game.current.playable")),
        unsafe_allow_html=True,
    )
    action_choices = screen.observation.action_choices
    selected_action_type = st.radio(
        catalog.t(lang, "game.current.playable"),
        [choice.action_type for choice in action_choices],
        format_func=lambda value: _action_choice_label(_find_action_choice(action_choices, value)),
        horizontal=True,
        label_visibility="collapsed",
    )
    selected_action = _find_action_choice(action_choices, str(selected_action_type))
    candidates = screen.observation.target_candidates.get(selected_action.action_type, [])
    target_labels = {seat.player_id: seat.name for seat in screen.seats}

    target_id = None
    if selected_action.requires_target:
        if candidates:
            selected_target = st.selectbox(
                catalog.t(lang, "action.target"),
                candidates,
                format_func=lambda value: target_labels.get(str(value), str(value)),
            )
            target_id = str(selected_target) if selected_target else None
        else:
            st.warning(catalog.t(lang, "common.none"))

    message = None
    if selected_action.requires_message:
        message = st.text_area(
            catalog.t(lang, "action.message"),
            key=KEY_MESSAGE,
            placeholder=catalog.label(lang, "action", "speech"),
            max_chars=settings.streamlit_message_max_chars,
        )

    missing_target = selected_action.requires_target and not target_id
    if st.button(
        catalog.t(lang, "action.send"),
        type="primary",
        use_container_width=True,
        disabled=missing_target,
    ):
        if selected_action.requires_message and not str(message or "").strip():
            st.warning(catalog.label(lang, "action", "speech"))
            return
        try:
            submit_screen_action(
                api_url=api_url,
                settings=settings,
                game_id=selected_option.game_id,
                manual_player_id=manual_player_id,
                manual_token=selected_option.manual_token,
                action_type=selected_action.action_type,
                target_id=target_id,
                message=str(message).strip() if message else None,
            )
        except AppError as exc:
            st.error(exc.detail)
            return
        clear_message(st.session_state)
        try:
            _start_and_remember_advance_job(
                st,
                api_url=api_url,
                settings=settings,
                game_id=selected_option.game_id,
            )
        except AppError as exc:
            st.error(exc.detail)
            return
        st.rerun()


def _render_auto_advance_controls(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    if selected_option.manual_player_id is None:
        return

    st.markdown(command_divider_html(), unsafe_allow_html=True)
    st.markdown(advance_note_html(screen.hand_panel), unsafe_allow_html=True)
    notice = consume_auto_advance_notice(st.session_state)
    if notice:
        st.warning(notice)
    state = auto_advance_state(st.session_state, selected_option.game_id)
    if state.running:
        st.markdown(
            auto_progress_html(
                detail=catalog.t(lang, "action.auto_advance_running"),
                steps=state.steps,
                max_steps=settings.streamlit_max_auto_steps,
            ),
            unsafe_allow_html=True,
        )
        if st.button(
            catalog.t(lang, "action.auto_advance_pause"),
            use_container_width=True,
        ):
            pause_auto_advance(st.session_state)
            st.rerun()
    elif screen.hand_panel.can_advance and st.button(
        catalog.t(lang, "action.advance_one_step"),
        type="primary",
        use_container_width=True,
    ):
        start_auto_advance(st.session_state, selected_option.game_id)
        st.rerun()

    _render_auto_advance_fragment(
        st,
        settings=settings,
        api_url=api_url,
        selected_option=selected_option,
        catalog=catalog,
        lang=lang,
    )


def _render_advance_job_progress(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    notice = consume_auto_advance_notice(st.session_state)
    if notice:
        st.warning(notice)
    state = auto_advance_state(st.session_state, selected_option.game_id)
    st.markdown(
        auto_progress_html(
            detail=catalog.t(lang, "action.auto_advance_running"),
            steps=state.steps,
            max_steps=settings.streamlit_max_auto_steps,
        ),
        unsafe_allow_html=True,
    )
    _render_auto_advance_fragment(
        st,
        settings=settings,
        api_url=api_url,
        selected_option=selected_option,
        catalog=catalog,
        lang=lang,
    )


def _start_and_remember_advance_job(
    st: Any,
    *,
    api_url: str,
    settings: AppSettings,
    game_id: str,
) -> None:
    job = start_advance_step(api_url=api_url, settings=settings, game_id=game_id)
    remember_advance_job(st.session_state, game_id=game_id, job_id=job.job_id)


def _render_auto_advance_fragment(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    current_job_id = advance_job_id(st.session_state, selected_option.game_id)
    if (
        not auto_advance_state(st.session_state, selected_option.game_id).running
        and not current_job_id
    ):
        return

    def auto_advance_once() -> None:
        state = auto_advance_state(st.session_state, selected_option.game_id)
        job_id = advance_job_id(st.session_state, selected_option.game_id)
        if job_id:
            try:
                job = load_advance_job(
                    api_url=api_url,
                    settings=settings,
                    game_id=selected_option.game_id,
                    job_id=job_id,
                )
            except AppError as exc:
                clear_advance_job(st.session_state)
                pause_auto_advance(st.session_state, notice=exc.detail)
                st.rerun(scope="app")
            if job.status in ACTIVE_ADVANCE_JOB_STATUSES:
                return
            clear_advance_job(st.session_state)
            if job.status == ADVANCE_JOB_STATUS_FAILED:
                detail = job.error.detail if job.error is not None else ""
                pause_auto_advance(st.session_state, notice=detail)
                st.rerun(scope="app")
            if state.running:
                record_auto_advance_step(
                    st.session_state,
                    game_id=selected_option.game_id,
                    now=time.monotonic(),
                )
            st.rerun(scope="app")

        if not state.running:
            return
        now = time.monotonic()
        interval = settings.streamlit_auto_advance_interval_seconds
        if state.last_step_at and now - state.last_step_at < interval:
            return
        if state.steps >= settings.streamlit_max_auto_steps:
            pause_auto_advance(
                st.session_state,
                notice=catalog.t(lang, "game.advance.limit"),
            )
            st.rerun(scope="app")
        try:
            _start_and_remember_advance_job(
                st,
                api_url=api_url,
                settings=settings,
                game_id=selected_option.game_id,
            )
        except AppError as exc:
            pause_auto_advance(st.session_state, notice=exc.detail)
            st.rerun(scope="app")
        st.rerun(scope="app")

    st.fragment(run_every=settings.streamlit_auto_advance_interval_seconds)(auto_advance_once)()


def _selected_option_index(options: list[SavedGameOptionView], selected_id: str) -> int:
    for index, option in enumerate(options):
        if option.option_id == selected_id:
            return index
    return 0


def _selected_option_by_id(
    options: list[SavedGameOptionView],
    selected_id: str,
) -> SavedGameOptionView | None:
    for option in options:
        if option.option_id == selected_id:
            return option
    return None


def _find_action_choice(
    action_choices: list[ActionChoiceView],
    action_type: object,
) -> ActionChoiceView:
    for choice in action_choices:
        if choice.action_type == str(action_type):
            return choice
    return action_choices[0]


def _action_choice_label(action: ActionChoiceView) -> str:
    return f"{action.icon} {action.label}"


def _streamlit() -> Any:
    return importlib.import_module("streamlit")


main()
