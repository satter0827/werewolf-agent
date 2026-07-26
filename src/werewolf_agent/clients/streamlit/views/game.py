"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

from werewolf_agent.clients.streamlit.components import (
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
from werewolf_agent.clients.streamlit.constants import (
    DEFAULT_NARRATION_MODE,
)
from werewolf_agent.clients.streamlit.events import (
    LOG_STREAMLIT_GAME_CREATE_FAILED,
)
from werewolf_agent.clients.streamlit.history import (
    create_session_game_selection,
)
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    create_game_from_setup,
    load_advance_job,
    start_advance_step,
    submit_screen_action,
)
from werewolf_agent.clients.streamlit.screens import (
    ScreenCatalog,
    ScreenElement,
)
from werewolf_agent.clients.streamlit.setup import (
    VIEW_GAME,
    VIEW_OBSERVE_SETUP,
    VIEW_PLAY_SETUP,
    remember_character_assignment,
    remember_manual_player_id,
    remember_narration_mode,
    remember_role_counts,
    remember_rules,
    remember_scenario_id,
    remember_seed_text,
    remember_setup_preset_id,
    seed_from_text,
    switch_view,
)
from werewolf_agent.clients.streamlit.state import (
    KEY_MESSAGE,
    advance_job_id,
    auto_advance_state,
    clear_advance_job,
    clear_message,
    consume_auto_advance_notice,
    pause_auto_advance,
    record_auto_advance_step,
    remember_active_game_selection,
    remember_advance_job,
    remember_selected_history,
    start_auto_advance,
)
from werewolf_agent.clients.streamlit.view_models import (
    ActionChoiceView,
    GameScreenView,
    SavedGameOptionView,
)
from werewolf_agent.contracts import (
    ACTIVE_ADVANCE_JOB_STATUSES,
    ADVANCE_JOB_STATUS_FAILED,
    AppError,
)
from werewolf_agent.contracts.error_catalog import get_error_spec
from werewolf_agent.contracts.schemas import (
    CustomCharacterDefinitionRequest,
    CustomRoleDefinitionRequest,
    LocalRulesSettings,
    NarrationMode,
)
from werewolf_agent.observability.constants import (
    EVENT_OUTCOME_FAILURE,
)
from werewolf_agent.observability.levels import log_level_number
from werewolf_agent.security.redaction import redact_text
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


def _render_game_screen(
    st: Any,
    *,
    settings: AppSettings,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
    message_max_chars: int,
    screens: ScreenCatalog,
) -> None:
    """Render the active game screen from its screen definition."""
    for element in screens.elements("game", "top"):
        if element.id == "status_bar":
            _render_status_bar(st, screen)

    layout = screens.layout("game")
    table_column, hand_column = st.columns(layout.columns, gap=layout.gap)
    with table_column:
        for element in screens.elements("game", "main"):
            _render_game_main_element(
                st,
                element,
                settings=settings,
                screen=screen,
                selected_option=selected_option,
                catalog=catalog,
                lang=lang,
                screens=screens,
            )
    with hand_column:
        _render_action_panel(
            st,
            settings=settings,
            screen=screen,
            selected_option=selected_option,
            catalog=catalog,
            lang=lang,
            message_max_chars=message_max_chars,
            screens=screens,
        )

    for element in screens.elements("game", "bottom"):
        if element.id == "timeline":
            _render_timeline(
                st, screen, variant=element.variant or "mobile", catalog=catalog, lang=lang
            )


def _render_game_main_element(
    st: Any,
    element: ScreenElement,
    *,
    settings: AppSettings,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
    screens: ScreenCatalog,
) -> None:
    """Render one configured main game element."""
    if element.id == "game_table":
        _render_game_table(st, screen, catalog=catalog, lang=lang)
    elif element.id == "timeline":
        _render_timeline(
            st, screen, variant=element.variant or "desktop", catalog=catalog, lang=lang
        )
    elif element.id == "next_actions":
        _render_next_actions(
            st,
            settings=settings,
            screen=screen,
            selected_option=selected_option,
            catalog=catalog,
            lang=lang,
            column_count=cast(int, screens.layout("game").next_action_columns),
        )


def _create_game(
    st: Any,
    *,
    feedback: Any,
    settings: AppSettings,
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
        if isinstance(exc, AppError):
            log_level = log_level_number(get_error_spec(exc.code).log_level)
            error_extra = exc.log_extra()
            error_message = exc.detail
        else:
            log_level = logging.INFO
            error_extra = {}
            error_message = str(exc)
        logger.log(
            log_level,
            LOG_STREAMLIT_GAME_CREATE_FAILED,
            extra={
                **error_extra,
                "error_message": redact_text(error_message),
                "error.message": redact_text(error_message),
                "event_action": LOG_STREAMLIT_GAME_CREATE_FAILED,
                "event_outcome": EVENT_OUTCOME_FAILURE,
                "manual_player_id": manual_player_id or "",
                "screen_mode": screen_mode,
            },
        )
        feedback.error(str(exc))
        return

    selection = create_session_game_selection(
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
    remember_active_game_selection(st.session_state, selection)
    remember_selected_history(st.session_state, f"session:{selection.selection_id}")
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
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
    column_count: int,
) -> None:
    if not screen.is_completed:
        return
    role_counts_value = selected_option.role_counts
    rules_value = selected_option.rules
    if not role_counts_value or rules_value is None:
        st.caption(catalog.t(lang, "next_actions.saved_hint"))
        return

    st.divider()
    action_columns = st.columns(column_count)
    first, second, third, fourth = action_columns[:4]
    if first.button(catalog.t(lang, "next_actions.random_seed"), use_container_width=True):
        _create_game(
            st,
            feedback=st,
            settings=settings,
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
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
    message_max_chars: int,
    screens: ScreenCatalog,
) -> None:
    elements = screens.elements("game", "side")
    if not elements:
        return
    has_active_job = bool(advance_job_id(st.session_state, selected_option.game_id))
    is_playable = screen.screen_mode != "observer"

    with st.container(border=False, key="right_command_panel"):
        for element in elements:
            if element.id == "hand_panel":
                st.markdown(hand_panel_html(screen.hand_panel), unsafe_allow_html=True)
            elif (
                element.id == "observer_log" and not is_playable and screen.observer_log is not None
            ):
                st.markdown(observer_log_html(screen.observer_log), unsafe_allow_html=True)
            elif element.id == "observation" and is_playable and screen.observation is not None:
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
            elif (
                element.id == "advance_job"
                and is_playable
                and not screen.is_completed
                and has_active_job
            ):
                _render_advance_job_progress(
                    st,
                    settings=settings,
                    selected_option=selected_option,
                    catalog=catalog,
                    lang=lang,
                )
            elif (
                element.id == "action_form"
                and is_playable
                and not screen.is_completed
                and not has_active_job
                and screen.can_submit_action
            ):
                _render_action_form(
                    st,
                    settings=settings,
                    screen=screen,
                    selected_option=selected_option,
                    catalog=catalog,
                    lang=lang,
                    message_max_chars=message_max_chars,
                )
            elif (
                element.id == "auto_advance"
                and is_playable
                and not screen.is_completed
                and not has_active_job
                and not screen.can_submit_action
            ):
                _render_auto_advance_controls(
                    st,
                    settings=settings,
                    screen=screen,
                    selected_option=selected_option,
                    catalog=catalog,
                    lang=lang,
                )
            elif element.id == "observation_memo":
                st.markdown(observation_memo_html(screen.observation_memo), unsafe_allow_html=True)


def _render_action_form(
    st: Any,
    *,
    settings: AppSettings,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
    message_max_chars: int,
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
            max_chars=message_max_chars,
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
                settings=settings,
                game_id=selected_option.game_id,
                manual_player_id=manual_player_id,
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
        type="secondary",
        use_container_width=True,
    ):
        start_auto_advance(st.session_state, selected_option.game_id)
        st.rerun()

    _render_auto_advance_fragment(
        st,
        settings=settings,
        selected_option=selected_option,
        catalog=catalog,
        lang=lang,
    )


def _render_advance_job_progress(
    st: Any,
    *,
    settings: AppSettings,
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
        selected_option=selected_option,
        catalog=catalog,
        lang=lang,
    )


def _start_and_remember_advance_job(
    st: Any,
    *,
    settings: AppSettings,
    game_id: str,
) -> None:
    job = start_advance_step(settings=settings, game_id=game_id)
    remember_advance_job(st.session_state, game_id=game_id, job_id=job.job_id)


def _render_auto_advance_fragment(
    st: Any,
    *,
    settings: AppSettings,
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
