"""Playable Streamlit entry point for one human player."""

from __future__ import annotations

import importlib
import secrets
import time
from typing import Any, cast
from uuid import uuid4

from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.schemas import LocalRulesSettings, RulesetResponse
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
    current_language,
    load_i18n,
    remember_language,
)
from werewolf_agent.interface.entrypoint.streamlit.operations import (
    advance_one_step,
    check_connection,
    create_game_from_setup,
    list_recent_games,
    load_game_screen,
    load_ruleset,
    log_streamlit_rerun_started,
    submit_screen_action,
)
from werewolf_agent.interface.entrypoint.streamlit.saves import (
    build_saved_game_options,
    create_save_slot,
    load_save_slots,
    upsert_save_slot,
)
from werewolf_agent.interface.entrypoint.streamlit.setup import (
    KEY_SETUP_PRESET,
    KEY_SETUP_ROLE_COUNTS,
    PRESET_STANDARD,
    PRESETS,
    VIEW_GAME,
    VIEW_OBSERVER_SETUP,
    VIEW_SETTINGS,
    VIEW_SETUP,
    current_view,
    preset_counts,
    remember_role_counts,
    remember_rules,
    remember_seed_text,
    role_counts,
    rules,
    seat_options,
    seed_from_text,
    seed_text,
    setup_summary,
    switch_view,
    validate_setup,
)
from werewolf_agent.interface.entrypoint.streamlit.state import (
    KEY_API_URL,
    KEY_MESSAGE,
    KEY_SELECTED_SAVE_ID,
    auto_advance_state,
    clear_message,
    consume_auto_advance_notice,
    control_tokens_by_slot,
    pause_auto_advance,
    record_auto_advance_step,
    remember_control_token,
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
    lang = current_language(st.session_state, settings)
    st.set_page_config(
        page_title=settings.streamlit_page_title,
        page_icon="🐺",
        layout="wide",
        initial_sidebar_state=settings.streamlit_initial_sidebar_state,
    )
    st.markdown(STREAMLIT_CSS, unsafe_allow_html=True)

    api_url, selected_option, view = _render_sidebar(st, settings, catalog=catalog, lang=lang)
    if view == VIEW_SETTINGS:
        _render_settings_screen(st, settings=settings, api_url=api_url, catalog=catalog, lang=lang)
        return
    if view != VIEW_GAME or selected_option is None:
        _render_setup_screen(
            st,
            settings=settings,
            api_url=api_url,
            catalog=catalog,
            lang=lang,
            observer=view == VIEW_OBSERVER_SETUP,
        )
        return

    sync_auto_advance_game(st.session_state, selected_option.game_id)
    try:
        screen = load_game_screen(
            api_url=api_url,
            settings=settings,
            game_id=selected_option.game_id,
            human_player_id=selected_option.human_player_id,
            control_token=selected_option.control_token,
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
    st.sidebar.divider()

    st.sidebar.subheader(catalog.t(lang, "sidebar.api"))
    default_api_url = text_value(
        st.session_state,
        KEY_API_URL,
        settings.streamlit_resolved_api_url,
    )
    api_url = str(
        st.sidebar.text_input(catalog.t(lang, "sidebar.api_base_url"), value=default_api_url)
    )
    st.session_state[KEY_API_URL] = api_url
    if st.sidebar.button(catalog.t(lang, "sidebar.check_connection"), use_container_width=True):
        try:
            check_connection(api_url=api_url, settings=settings)
        except AppError as exc:
            st.sidebar.error(exc.detail)
        else:
            st.sidebar.success(catalog.t(lang, "sidebar.connected"))

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
        switch_view(st.session_state, VIEW_SETUP)
        st.rerun()
    if st.sidebar.button(f"⚙ {catalog.t(lang, 'nav.settings')}", use_container_width=True):
        switch_view(st.session_state, VIEW_SETTINGS)
        st.rerun()
    if st.sidebar.button(f"◉ {catalog.t(lang, 'nav.observe')}", use_container_width=True):
        switch_view(st.session_state, VIEW_OBSERVER_SETUP)
        st.rerun()
    st.sidebar.button(
        f"□ {catalog.t(lang, 'nav.history')}",
        use_container_width=True,
        disabled=True,
    )
    st.sidebar.button(
        f"⌁ {catalog.t(lang, 'nav.diagnostics')}",
        use_container_width=True,
        disabled=True,
    )
    st.sidebar.markdown(
        f"""
        <div class="wa-help-card">
            <b>{catalog.t(lang, "app.help.title")}</b><br>
            {catalog.t(lang, "app.help.text")}
        </div>
        """,
        unsafe_allow_html=True,
    )
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
        runs = list_recent_games(api_url=api_url, settings=settings)
    except AppError:
        runs = []
        st.sidebar.caption(catalog.t(lang, "save.unavailable"))
    options = build_saved_game_options(
        slots,
        runs,
        catalog=catalog,
        lang=lang,
        control_tokens=control_tokens_by_slot(st.session_state),
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
        ruleset = load_ruleset(api_url=api_url, settings=settings)
    except AppError as exc:
        st.error(exc.detail)
        return

    st.header(catalog.t(lang, "setup.title.observe" if observer else "setup.title.play"))
    st.caption(catalog.t(lang, "setup.mode.observe" if observer else "setup.mode.play"))
    selected_preset = st.selectbox(
        catalog.t(lang, "setup.preset"),
        list(PRESETS),
        index=list(PRESETS).index(text_value(st.session_state, KEY_SETUP_PRESET, PRESET_STANDARD))
        if text_value(st.session_state, KEY_SETUP_PRESET, PRESET_STANDARD) in PRESETS
        else 0,
        format_func=lambda value: catalog.label(lang, "preset", value),
    )
    if selected_preset != st.session_state.get(KEY_SETUP_PRESET):
        counts = preset_counts(str(selected_preset), ruleset)
        remember_role_counts(st.session_state, counts)
        for role_id, count in counts.items():
            st.session_state[_role_count_key(role_id)] = count
        st.session_state[KEY_SETUP_PRESET] = str(selected_preset)
        st.rerun()

    counts = _render_role_counts(st, ruleset, catalog=catalog, lang=lang)
    active_rules = rules(st.session_state, ruleset)
    validation = validate_setup(counts, ruleset, catalog=catalog, lang=lang)
    total_players = sum(counts.values())
    st.metric(catalog.t(lang, "setup.total_players"), f"{total_players}")
    for message in validation.messages:
        st.warning(message)

    seats = seat_options(counts)
    human_player_id = None if observer else _render_human_seat_selector(st, seats, catalog, lang)
    seed_value = _render_seed_controls(st, settings, catalog, lang)
    st.caption(
        setup_summary(
            counts,
            rules=active_rules,
            ruleset=ruleset,
            catalog=catalog,
            lang=lang,
        )
    )

    disabled = not validation.is_valid or (human_player_id is None and not observer)
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
            human_player_id=None if observer else str(human_player_id),
            screen_mode="observer" if observer else "playable",
            catalog=catalog,
            lang=lang,
        )


def _render_role_counts(
    st: Any,
    ruleset: RulesetResponse,
    *,
    catalog: I18nCatalog,
    lang: Language,
) -> dict[str, int]:
    counts = role_counts(st.session_state, ruleset)
    st.subheader(catalog.t(lang, "setup.role_counts"))
    next_counts: dict[str, int] = {}
    for role in ruleset.roles:
        widget_key = _role_count_key(role.id)
        if widget_key not in st.session_state:
            st.session_state[widget_key] = int(counts.get(role.id, 0))
        next_counts[role.id] = int(
            st.number_input(
                catalog.label(lang, "role", role.id),
                min_value=0,
                max_value=ruleset.player_count["max"],
                step=1,
                key=widget_key,
                help=(
                    f"{catalog.label(lang, 'faction', role.faction)} / {', '.join(role.abilities)}"
                ),
            )
        )
    remember_role_counts(st.session_state, next_counts)
    return next_counts


def _render_human_seat_selector(
    st: Any,
    seats: list[tuple[str, str]],
    catalog: I18nCatalog,
    lang: Language,
) -> str | None:
    if not seats:
        st.warning(catalog.t(lang, "setup.no_seats"))
        return None
    return str(
        st.selectbox(
            catalog.t(lang, "setup.seat"),
            seats,
            index=0,
            format_func=lambda option: option[1],
        )[0]
    )


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
    try:
        ruleset = load_ruleset(api_url=api_url, settings=settings)
    except AppError as exc:
        st.error(exc.detail)
        return

    st.header(catalog.t(lang, "settings.title"))
    st.caption(catalog.t(lang, "settings.caption"))
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

    current_rules = rules(st.session_state, ruleset)
    st.subheader(catalog.t(lang, "settings.local_rules"))
    with st.form("streamlit-settings-rules"):
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
        apply_clicked = st.form_submit_button(
            catalog.t(lang, "common.apply"),
            use_container_width=True,
        )
        reset_clicked = st.form_submit_button(
            catalog.t(lang, "common.default"),
            use_container_width=True,
        )
    if reset_clicked:
        remember_rules(st.session_state, ruleset.default_rules)
        st.success(catalog.t(lang, "settings.reset"))
        st.rerun()
    if apply_clicked:
        remember_rules(
            st.session_state,
            LocalRulesSettings(
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
            ),
        )
        st.success(catalog.t(lang, "settings.saved"))


def _role_count_key(role_id: str) -> str:
    return f"{KEY_SETUP_ROLE_COUNTS}:{role_id}"


def _create_game(
    st: Any,
    *,
    feedback: Any,
    settings: AppSettings,
    api_url: str,
    role_counts: dict[str, int],
    rules: LocalRulesSettings,
    seed_text: str,
    human_player_id: str | None,
    screen_mode: str,
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
            human_player_id=human_player_id,
        )
    except (AppError, ValueError) as exc:
        feedback.error(str(exc))
        return

    control_token = (created.control_tokens or {}).get(human_player_id or "", "")
    slot = create_save_slot(
        created,
        human_player_id=human_player_id,
        role_counts=role_counts,
        rules=rules,
        seed=seed_from_text(seed_text),
    )
    upsert_save_slot(settings.streamlit_save_file_path, slot)
    remember_control_token(
        st.session_state,
        slot_id=slot.slot_id,
        control_token=control_token,
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
            human_player_id=selected_option.human_player_id
            if selected_option.mode == "playable"
            else None,
            screen_mode=selected_option.mode,
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
            human_player_id=selected_option.human_player_id
            if selected_option.mode == "playable"
            else None,
            screen_mode=selected_option.mode,
            catalog=catalog,
            lang=lang,
        )
    if third.button(catalog.t(lang, "next_actions.return_setup"), use_container_width=True):
        remember_role_counts(st.session_state, role_counts_value)
        remember_rules(st.session_state, rules_value)
        remember_seed_text(st.session_state, same_seed_text)
        switch_view(
            st.session_state,
            VIEW_SETUP if selected_option.mode == "playable" else VIEW_OBSERVER_SETUP,
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
    human_player_id = selected_option.human_player_id
    if screen.observation is None or human_player_id is None:
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
                human_player_id=human_player_id,
                control_token=selected_option.control_token,
                action_type=selected_action.action_type,
                target_id=target_id,
                message=str(message).strip() if message else None,
            )
        except AppError as exc:
            st.error(exc.detail)
            return
        clear_message(st.session_state)
        try:
            advance_one_step(
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
    if selected_option.human_player_id is None:
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
        catalog.t(lang, "action.advance_until_input"),
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


def _render_auto_advance_fragment(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
) -> None:
    if not auto_advance_state(st.session_state, selected_option.game_id).running:
        return

    def auto_advance_once() -> None:
        state = auto_advance_state(st.session_state, selected_option.game_id)
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
            advance_one_step(
                api_url=api_url,
                settings=settings,
                game_id=selected_option.game_id,
            )
        except AppError as exc:
            pause_auto_advance(st.session_state, notice=exc.detail)
            st.rerun(scope="app")
        record_auto_advance_step(
            st.session_state,
            game_id=selected_option.game_id,
            now=now,
        )
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
