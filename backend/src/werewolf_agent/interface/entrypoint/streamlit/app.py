"""Playable Streamlit entry point for one human player."""

from __future__ import annotations

import importlib
from typing import Any, cast
from uuid import uuid4

from werewolf_agent.contracts import AppError
from werewolf_agent.interface.entrypoint.streamlit.components import (
    advance_note_html,
    game_table_html,
    hand_panel_html,
    observation_panel_html,
    status_grid_html,
    timeline_section_html,
)
from werewolf_agent.interface.entrypoint.streamlit.operations import (
    advance_until_input,
    check_connection,
    create_playable_game,
    list_recent_games,
    load_game_screen,
    log_streamlit_rerun_started,
    submit_screen_action,
)
from werewolf_agent.interface.entrypoint.streamlit.saves import (
    build_saved_game_options,
    create_save_slot,
    load_save_slots,
    upsert_save_slot,
)
from werewolf_agent.interface.entrypoint.streamlit.state import (
    KEY_API_URL,
    KEY_MESSAGE,
    KEY_SELECTED_SAVE_ID,
    clear_message,
    control_tokens_by_slot,
    remember_control_token,
    remember_selected_save,
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
    st.set_page_config(
        page_title=settings.streamlit_page_title,
        page_icon="🐺",
        layout="wide",
        initial_sidebar_state=settings.streamlit_initial_sidebar_state,
    )
    st.html(STREAMLIT_CSS)

    api_url, selected_option = _render_sidebar(st, settings)
    if selected_option is None:
        _render_empty_state(st, settings=settings, api_url=api_url)
        return

    try:
        screen = load_game_screen(
            api_url=api_url,
            settings=settings,
            game_id=selected_option.game_id,
            human_player_id=selected_option.human_player_id,
            control_token=selected_option.control_token,
            screen_mode=selected_option.mode,
        )
    except AppError as exc:
        st.error(exc.detail)
        return

    _render_status_bar(st, screen)
    table_column, hand_column = st.columns([2.15, 1], gap="medium")
    with table_column:
        _render_game_table(st, screen)
        _render_timeline(st, screen, variant="desktop")
    with hand_column:
        _render_action_panel(
            st,
            settings=settings,
            api_url=api_url,
            screen=screen,
            selected_option=selected_option,
        )
    _render_timeline(st, screen, variant="mobile")


def _render_sidebar(st: Any, settings: AppSettings) -> tuple[str, SavedGameOptionView | None]:
    _render_sidebar_brand(st)
    st.sidebar.divider()

    st.sidebar.subheader("API 接続")
    default_api_url = text_value(
        st.session_state,
        KEY_API_URL,
        settings.streamlit_resolved_api_url,
    )
    api_url = str(st.sidebar.text_input("API Base URL", value=default_api_url))
    st.session_state[KEY_API_URL] = api_url
    if st.sidebar.button("接続を確認", use_container_width=True):
        try:
            check_connection(api_url=api_url, settings=settings)
        except AppError as exc:
            st.sidebar.error(exc.detail)
        else:
            st.sidebar.success("接続済み")

    st.sidebar.divider()
    st.sidebar.subheader("保存データ")
    selected_option = _render_save_selector(st, settings=settings, api_url=api_url)

    st.sidebar.divider()
    st.sidebar.subheader("新しいゲーム")
    _render_create_game(
        st,
        container=st.sidebar,
        form_key="create-game-sidebar",
        settings=settings,
        api_url=api_url,
    )

    st.sidebar.divider()
    st.sidebar.subheader("ナビゲーション")
    st.sidebar.markdown(
        """
        <div class="wa-nav-list">
            <div class="wa-nav-item wa-nav-item-active">▶ プレイ</div>
            <div class="wa-nav-item">◉ 観戦</div>
            <div class="wa-nav-item">□ 履歴</div>
            <div class="wa-nav-item">⚙ 設定</div>
            <div class="wa-nav-item">⌁ 診断</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        """
        <div class="wa-help-card">
            <b>このページについて</b><br>
            画面の見方やルールを確認できます
        </div>
        """,
        unsafe_allow_html=True,
    )
    return api_url, selected_option


def _render_sidebar_brand(st: Any) -> None:
    st.sidebar.markdown(
        """
        <div class="wa-sidebar-brand">
            <div class="wa-brand-mark">🐺</div>
            <div>
                <div class="wa-brand-title">Werewolf Agent</div>
                <div class="wa-brand-mode">プレイモード</div>
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
) -> SavedGameOptionView | None:
    slots = load_save_slots(settings.streamlit_save_file_path)
    try:
        runs = list_recent_games(api_url=api_url, settings=settings)
    except AppError:
        runs = []
        st.sidebar.caption("保存データは API 接続後に更新されます。")
    options = build_saved_game_options(
        slots,
        runs,
        control_tokens=control_tokens_by_slot(st.session_state),
    )
    if not options:
        st.sidebar.caption("保存データはまだありません。")
        return None

    selected_id = text_value(st.session_state, KEY_SELECTED_SAVE_ID)
    index = _selected_option_index(options, selected_id)
    selected_option = cast(
        SavedGameOptionView,
        st.sidebar.selectbox(
            "保存データを選択",
            options,
            index=index,
            format_func=lambda option: option.label,
        ),
    )
    remember_selected_save(st.session_state, selected_option.option_id)
    return selected_option


def _render_create_game(
    st: Any,
    *,
    container: Any,
    form_key: str,
    settings: AppSettings,
    api_url: str,
) -> None:
    with container.form(form_key):
        player_count = st.number_input(
            "プレイヤー数",
            min_value=settings.game_min_players,
            max_value=settings.game_max_players,
            value=settings.game_default_player_count,
            step=1,
        )
        seed_text = st.text_input("シード", value=str(settings.streamlit_default_seed))
        seat_options = _human_seat_options(int(player_count))
        default_human = settings.streamlit_default_human_player_id
        default_index = next(
            (index for index, option in enumerate(seat_options) if option[0] == default_human),
            0,
        )
        selected_seat = st.selectbox(
            "あなたの席",
            seat_options,
            index=default_index,
            format_func=lambda option: option[1],
        )
        submitted = st.form_submit_button("新しいゲームを始める", use_container_width=True)
    if submitted:
        _create_game(
            st,
            feedback=container,
            settings=settings,
            api_url=api_url,
            player_count=int(player_count),
            seed_text=seed_text,
            human_player_id=cast(tuple[str, str], selected_seat)[0],
        )


def _create_game(
    st: Any,
    *,
    feedback: Any,
    settings: AppSettings,
    api_url: str,
    player_count: int,
    seed_text: str,
    human_player_id: str,
) -> None:
    try:
        created = create_playable_game(
            api_url=api_url,
            settings=settings,
            player_count=player_count,
            seed_text=seed_text,
            human_player_id=human_player_id,
        )
    except (AppError, ValueError) as exc:
        feedback.error(str(exc))
        return

    control_token = (created.control_tokens or {}).get(human_player_id, "")
    slot = create_save_slot(
        created,
        human_player_id=human_player_id,
    )
    upsert_save_slot(settings.streamlit_save_file_path, slot)
    remember_control_token(
        st.session_state,
        slot_id=slot.slot_id,
        control_token=control_token,
    )
    remember_selected_save(st.session_state, f"slot:{slot.slot_id}")
    clear_message(st.session_state)
    feedback.success("ゲームを作成しました")
    st.rerun()


def _render_empty_state(st: Any, *, settings: AppSettings, api_url: str) -> None:
    st.info("新しいゲームを始めるか、保存データを選んでください。")
    _render_create_game(
        st,
        container=st,
        form_key="create-game-main",
        settings=settings,
        api_url=api_url,
    )


def _render_status_bar(st: Any, screen: GameScreenView) -> None:
    st.markdown(status_grid_html(screen.status_metrics), unsafe_allow_html=True)


def _render_game_table(st: Any, screen: GameScreenView) -> None:
    st.markdown(game_table_html(screen), unsafe_allow_html=True)


def _render_timeline(st: Any, screen: GameScreenView, *, variant: str) -> None:
    st.markdown(timeline_section_html(screen.timeline, variant=variant), unsafe_allow_html=True)


def _render_action_panel(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
) -> None:
    st.markdown(hand_panel_html(screen.hand_panel), unsafe_allow_html=True)
    if screen.screen_mode == "observer":
        st.caption("公開情報だけを表示しています。")
        return

    if screen.observation is not None:
        st.markdown(observation_panel_html(screen.observation), unsafe_allow_html=True)

    if screen.is_completed:
        return

    if screen.can_submit_action:
        _render_action_form(
            st,
            settings=settings,
            api_url=api_url,
            screen=screen,
            selected_option=selected_option,
        )
        return

    st.divider()
    st.markdown(advance_note_html(screen.hand_panel), unsafe_allow_html=True)
    if screen.hand_panel.can_advance and st.button(
        "次の入力待ちまで進める",
        type="primary",
        use_container_width=True,
    ):
        _run_until_input(
            st,
            settings=settings,
            api_url=api_url,
            selected_option=selected_option,
        )


def _render_action_form(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    selected_option: SavedGameOptionView,
) -> None:
    human_player_id = selected_option.human_player_id
    if screen.observation is None or human_player_id is None:
        return

    st.divider()
    st.markdown("#### 利用可能な行動")
    action_choices = screen.observation.action_choices
    selected_action_type = st.radio(
        "行動",
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
                "対象を選ぶ",
                candidates,
                format_func=lambda value: target_labels.get(str(value), str(value)),
            )
            target_id = str(selected_target) if selected_target else None
        else:
            st.warning("選べる対象がありません。")

    message = None
    if selected_action.requires_message:
        message = st.text_area(
            "発言内容",
            key=KEY_MESSAGE,
            placeholder="ここに発言内容を入力してください...",
            max_chars=settings.streamlit_message_max_chars,
        )

    missing_target = selected_action.requires_target and not target_id
    if st.button(
        "入力を送信",
        type="primary",
        use_container_width=True,
        disabled=missing_target,
    ):
        if selected_action.requires_message and not str(message or "").strip():
            st.warning("発言内容を入力してください。")
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
        st.success("入力を送信しました。")
        if settings.streamlit_auto_advance_after_action:
            _run_until_input(
                st,
                settings=settings,
                api_url=api_url,
                selected_option=selected_option,
            )
            return
        st.rerun()


def _run_until_input(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    selected_option: SavedGameOptionView,
) -> None:
    human_player_id = selected_option.human_player_id
    if human_player_id is None:
        return
    try:
        result = advance_until_input(
            api_url=api_url,
            settings=settings,
            game_id=selected_option.game_id,
        )
    except AppError as exc:
        st.error(exc.detail)
        return
    if result.completed or result.reached_input:
        st.rerun()
        return
    if result.hit_limit:
        st.warning("進行の上限に達しました。現在の状態を確認してください。")


def _selected_option_index(options: list[SavedGameOptionView], selected_id: str) -> int:
    for index, option in enumerate(options):
        if option.option_id == selected_id:
            return index
    return 0


def _human_seat_options(player_count: int) -> list[tuple[str, str]]:
    return [(f"player-{index}", f"P{index}") for index in range(1, player_count + 1)]


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
