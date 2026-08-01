"""Playable Streamlit interface for one manual player."""

from __future__ import annotations

import logging
import time
from typing import Any

from werewolf_agent.clients.presentation import implements_features
from werewolf_agent.clients.streamlit.components import (
    game_table_html,
    status_grid_html,
    timeline_section_html,
)
from werewolf_agent.clients.streamlit.i18n import (
    I18nCatalog,
    Language,
)
from werewolf_agent.clients.streamlit.operations import (
    load_advance_job,
    start_advance_step,
    submit_screen_action,
)
from werewolf_agent.clients.streamlit.setup import (
    VIEW_OBSERVE_SETUP,
    VIEW_PLAY_SETUP,
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
    remember_advance_job,
    start_auto_advance,
)
from werewolf_agent.clients.streamlit.view_models import (
    ActionChoiceView,
    GameScreenView,
    SavedGameOptionView,
)
from werewolf_agent.clients.streamlit.views.errors import render_app_error
from werewolf_agent.contracts import (
    ACTIVE_ADVANCE_JOB_STATUSES,
    ADVANCE_JOB_STATUS_FAILED,
    AppError,
)
from werewolf_agent.settings import (
    AppSettings,
)

logger = logging.getLogger(__name__)
STREAMLIT_AUTH_SESSION_KEY = "_auth_session"


@implements_features(
    "game_get",
    "game_timeline_get",
    "game_observation_get",
    "game_action_submit",
    "game_advance",
    "operation_get",
)
def _render_game_screen(
    st: Any,
    *,
    settings: AppSettings,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
    catalog: I18nCatalog,
    lang: Language,
    message_max_chars: int,
    mutations_available: bool = True,
) -> None:
    """Render the game as one tableau with an adjacent command rail."""
    st.title(catalog.t(lang, "game.workspace.title"))
    _render_status_bar(st, screen)
    if screen.result_summary is not None:
        _render_result_summary(st, screen)

    table_column, hand_column = st.columns((7, 3), gap="large")
    with table_column:
        _render_game_table(st, screen, catalog=catalog, lang=lang)
    with hand_column:
        _render_action_panel(
            st,
            settings=settings,
            screen=screen,
            selected_option=selected_option,
            catalog=catalog,
            lang=lang,
            message_max_chars=message_max_chars,
            mutations_available=mutations_available,
        )
    _render_next_actions(
        st,
        settings=settings,
        screen=screen,
        selected_option=selected_option,
        catalog=catalog,
        lang=lang,
        column_count=4,
    )
    _render_timeline(st, screen, variant="primary", catalog=catalog, lang=lang)


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
        ),
        unsafe_allow_html=True,
    )


def _render_result_summary(st: Any, screen: GameScreenView) -> None:
    """Lead a completed game with its outcome before the replay."""
    summary = screen.result_summary
    if summary is None:
        return
    with st.container(border=True, key="game_result_summary"):
        st.header(summary.title)
        st.write(summary.detail)
        for fact in summary.facts:
            st.caption(fact)


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
    st.divider()
    first, second = st.columns(2)
    if first.button(catalog.t(lang, "next_actions.return_setup"), width="stretch"):
        switch_view(
            st.session_state,
            VIEW_PLAY_SETUP if selected_option.mode == "playable" else VIEW_OBSERVE_SETUP,
        )
        st.rerun()
    if second.button(catalog.t(lang, "next_actions.saves"), width="stretch"):
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
    mutations_available: bool,
) -> None:
    has_active_job = bool(advance_job_id(st.session_state, selected_option.game_id))
    is_playable = screen.screen_mode != "observer"
    if is_playable and not mutations_available:
        st.warning(catalog.t(lang, "runtime.queue_required"))

    with st.container(border=False, key="right_command_panel"):
        st.badge(screen.hand_panel.heading, color=_badge_color(screen.hand_panel.tone))
        st.subheader(screen.hand_panel.title)
        st.write(screen.hand_panel.detail)

        if not is_playable and screen.observer_log is not None:
            st.subheader(screen.observer_log.title)
            st.caption(screen.observer_log.entries_title)
            if screen.observer_log.entries:
                for entry in screen.observer_log.entries:
                    st.write(entry)
            else:
                st.info(screen.observer_log.empty_text)
        elif is_playable and screen.observation is not None:
            st.subheader(catalog.t(lang, "observation.role_title"))
            st.badge(screen.observation.role, color="red")
            st.caption(catalog.t(lang, "game.role_note", role=screen.observation.role))
            st.subheader(catalog.t(lang, "observation.info_title"))
            if screen.observation.known_role_lines:
                for line in screen.observation.known_role_lines:
                    st.write(line)
            else:
                st.info(catalog.t(lang, "observation.empty"))

        if is_playable and not screen.is_completed and has_active_job:
            _render_advance_job_progress(
                st,
                settings=settings,
                selected_option=selected_option,
                catalog=catalog,
                lang=lang,
            )
        elif (
            is_playable
            and not screen.is_completed
            and screen.can_submit_action
            and mutations_available
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
        elif is_playable and not screen.is_completed and mutations_available:
            _render_auto_advance_controls(
                st,
                settings=settings,
                screen=screen,
                selected_option=selected_option,
                catalog=catalog,
                lang=lang,
            )

        with st.expander(screen.observation_memo.title, expanded=False):
            st.caption(screen.observation_memo.updated_label)
            for line in screen.observation_memo.lines:
                st.write(line)


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

    st.divider()
    st.subheader(catalog.t(lang, "game.current.playable"))
    action_choices = screen.observation.action_choices
    selected_action_type = st.segmented_control(
        catalog.t(lang, "game.current.playable"),
        [choice.action_type for choice in action_choices],
        format_func=lambda value: _action_choice_label(_find_action_choice(action_choices, value)),
        selection_mode="single",
        label_visibility="collapsed",
        key="game_action_type",
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
    missing_message = selected_action.requires_message and not str(message or "").strip()
    if missing_target:
        st.caption(catalog.t(lang, "action.target_required"))
    if missing_message:
        st.caption(catalog.t(lang, "action.message_required"))
    if st.button(
        catalog.t(lang, "action.send"),
        type="primary",
        width="stretch",
        disabled=missing_target or missing_message,
    ):
        try:
            submit_screen_action(
                settings=settings,
                game_id=selected_option.game_id,
                manual_player_id=manual_player_id,
                action_type=selected_action.action_type,
                ability_id=selected_action.ability_id,
                target_id=target_id,
                message=str(message).strip() if message else None,
            )
        except AppError as exc:
            render_app_error(st, exc, lang=lang)
            return
        clear_message(st.session_state)
        try:
            _start_and_remember_advance_job(
                st,
                settings=settings,
                game_id=selected_option.game_id,
            )
        except AppError as exc:
            render_app_error(st, exc, lang=lang)
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

    st.divider()
    st.subheader(screen.hand_panel.advance_title)
    st.caption(screen.hand_panel.advance_detail)
    notice = consume_auto_advance_notice(st.session_state)
    if notice:
        st.warning(notice)
    state = auto_advance_state(st.session_state, selected_option.game_id)
    if state.running:
        progress = st.status(
            catalog.t(lang, "action.auto_advance_running"),
            state="running",
            expanded=True,
            type="compact",
        )
        progress.write(f"{state.steps} / {settings.streamlit_max_auto_steps}")
        if st.button(
            catalog.t(lang, "action.auto_advance_pause"),
            width="stretch",
        ):
            pause_auto_advance(st.session_state)
            st.rerun()
    elif screen.hand_panel.can_advance and st.button(
        catalog.t(lang, "action.advance_one_step"),
        type="secondary",
        width="stretch",
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
    progress = st.status(
        catalog.t(lang, "action.auto_advance_running"),
        state="running",
        expanded=True,
        type="compact",
    )
    progress.write(f"{state.steps} / {settings.streamlit_max_auto_steps}")
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
    return action.label


def _badge_color(tone: str) -> str:
    """Map view-model tones to supported Streamlit badge colors."""
    return {
        "danger": "red",
        "success": "green",
        "warning": "orange",
        "info": "blue",
    }.get(tone, "gray")
