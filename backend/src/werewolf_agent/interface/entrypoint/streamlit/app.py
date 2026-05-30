"""Playable Streamlit entry point for one human player."""

from __future__ import annotations

import importlib
from typing import Any

from werewolf_agent.commons.configuration import AppSettings, get_settings
from werewolf_agent.contracts import AppError
from werewolf_agent.interface.entrypoint.streamlit.components import (
    advance_note_html,
    game_table_html,
    hand_panel_html,
    status_grid_html,
    timeline_header_html,
    timeline_html,
)
from werewolf_agent.interface.entrypoint.streamlit.operations import (
    advance_until_input,
    check_connection,
    create_playable_game,
    list_recent_games,
    load_game_screen,
    submit_screen_action,
)
from werewolf_agent.interface.entrypoint.streamlit.state import (
    KEY_API_URL,
    KEY_CONTROL_TOKEN,
    KEY_GAME_ID,
    KEY_HUMAN_PLAYER_ID,
    KEY_MESSAGE,
    clear_game_session,
    set_game_session,
    text_value,
)
from werewolf_agent.interface.entrypoint.streamlit.styles import STREAMLIT_CSS
from werewolf_agent.interface.entrypoint.streamlit.view_models import (
    ActionChoiceView,
    GameScreenView,
    game_run_option_label,
)


def main() -> None:
    """Render the Streamlit application."""
    st = _streamlit()
    settings = get_settings()
    st.set_page_config(page_title=settings.streamlit_page_title, page_icon="🐺", layout="wide")
    st.markdown(STREAMLIT_CSS, unsafe_allow_html=True)

    api_url = _render_sidebar(st, settings)
    game_id = text_value(st.session_state, KEY_GAME_ID)
    human_player_id = text_value(
        st.session_state,
        KEY_HUMAN_PLAYER_ID,
        settings.streamlit_default_human_player_id,
    )
    control_token = text_value(st.session_state, KEY_CONTROL_TOKEN)

    if not game_id:
        _render_empty_state(st)
        return

    try:
        screen = load_game_screen(
            api_url=api_url,
            settings=settings,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )
    except AppError as exc:
        st.error(exc.detail)
        return

    _render_status_bar(st, screen)
    table_column, hand_column = st.columns([2.15, 1], gap="medium")
    with table_column:
        _render_game_table(st, screen)
    with hand_column:
        _render_action_panel(
            st,
            settings=settings,
            api_url=api_url,
            screen=screen,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )

    timeline_column, _ = st.columns([2.15, 1], gap="medium")
    with timeline_column:
        _render_timeline(st, screen)


def _render_sidebar(st: Any, settings: AppSettings) -> str:
    st.sidebar.title("プレイ")
    st.sidebar.markdown('<div class="wa-sidebar-mode">Werewolf Agent</div>', unsafe_allow_html=True)
    st.sidebar.divider()
    st.sidebar.subheader("API 接続")
    default_api_url = text_value(
        st.session_state,
        KEY_API_URL,
        settings.streamlit_resolved_api_url,
    )
    api_url = str(st.sidebar.text_input("接続先", value=default_api_url))
    st.session_state[KEY_API_URL] = api_url
    if st.sidebar.button("接続を確認", use_container_width=True):
        try:
            check_connection(api_url=api_url, settings=settings)
        except AppError as exc:
            st.sidebar.error(exc.detail)
        else:
            st.sidebar.success("接続済み")

    st.sidebar.divider()
    st.sidebar.subheader("現在のゲーム")
    _render_current_game(st, settings=settings, api_url=api_url)

    st.sidebar.divider()
    st.sidebar.subheader("新しいゲーム")
    with st.sidebar.form("create-game"):
        player_count = st.number_input(
            "プレイヤー数",
            min_value=settings.game_min_players,
            max_value=settings.game_max_players,
            value=settings.game_default_player_count,
            step=1,
        )
        seed_text = st.text_input("シード", value=str(settings.streamlit_default_seed))
        player_options = [f"player-{index}" for index in range(1, int(player_count) + 1)]
        default_human = settings.streamlit_default_human_player_id
        selected_index = (
            player_options.index(default_human) if default_human in player_options else 0
        )
        human_player_id = st.selectbox(
            "あなたのプレイヤー",
            player_options,
            index=selected_index,
        )
        submitted = st.form_submit_button("新しいゲームを始める", use_container_width=True)
    if submitted:
        _create_game(
            st,
            settings=settings,
            api_url=api_url,
            player_count=int(player_count),
            seed_text=seed_text,
            human_player_id=str(human_player_id),
        )

    if st.sidebar.button("ゲーム選択をクリア", use_container_width=True):
        clear_game_session(st.session_state)
        st.rerun()

    return api_url


def _render_current_game(st: Any, *, settings: AppSettings, api_url: str) -> None:
    current_game_id = text_value(st.session_state, KEY_GAME_ID)
    current_human_player = text_value(
        st.session_state,
        KEY_HUMAN_PLAYER_ID,
        settings.streamlit_default_human_player_id,
    )
    current_control_key = text_value(st.session_state, KEY_CONTROL_TOKEN)
    if current_game_id:
        st.sidebar.caption(f"選択中: {current_game_id}")

    try:
        runs = list_recent_games(api_url=api_url, settings=settings)
    except AppError:
        runs = []
        st.sidebar.caption("ゲーム一覧は API 接続後に表示されます。")

    if runs:
        option_labels = [game_run_option_label(run) for run in runs]
        selected_label = st.sidebar.selectbox(
            "最近のゲーム",
            option_labels,
            label_visibility="collapsed",
            key="wa-current-game-select",
        )
        selected_run = runs[option_labels.index(selected_label)]
        human_player = st.sidebar.text_input(
            "操作するプレイヤー",
            value=current_human_player,
            key="wa-current-game-human-player",
        )
        control_key = st.sidebar.text_input(
            "操作用キー",
            value=current_control_key,
            type="password",
            key="wa-current-game-control-key",
        )
        if st.sidebar.button("このゲームを開く", use_container_width=True):
            set_game_session(
                st.session_state,
                game_id=selected_run.game_id,
                human_player_id=human_player,
                control_token=control_key,
            )
            st.rerun()
    elif not current_game_id:
        st.sidebar.caption("まだゲームがありません。")

    with st.sidebar.form("open-game-by-id"):
        game_id = st.text_input("ゲーム ID", value=current_game_id, key="wa-open-game-id")
        human_player = st.text_input(
            "操作するプレイヤー",
            value=current_human_player,
            key="wa-open-game-human-player",
        )
        control_key = st.text_input(
            "操作用キー",
            value=current_control_key,
            type="password",
            key="wa-open-game-control-key",
        )
        opened = st.form_submit_button("ゲームIDで開く", use_container_width=True)
    if opened and game_id and human_player and control_key:
        set_game_session(
            st.session_state,
            game_id=game_id,
            human_player_id=human_player,
            control_token=control_key,
        )
        st.rerun()


def _create_game(
    st: Any,
    *,
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
        st.sidebar.error(str(exc))
        return

    control_token = (created.control_tokens or {}).get(human_player_id, "")
    set_game_session(
        st.session_state,
        game_id=created.game_id,
        human_player_id=human_player_id,
        control_token=control_token,
    )
    st.sidebar.success("ゲームを作成しました")
    st.rerun()


def _render_empty_state(st: Any) -> None:
    st.info("サイドバーで API 接続を確認し、新しいゲームを始めてください。")


def _render_status_bar(st: Any, screen: GameScreenView) -> None:
    st.markdown(status_grid_html(screen.status_metrics), unsafe_allow_html=True)


def _render_game_table(st: Any, screen: GameScreenView) -> None:
    st.markdown(game_table_html(screen), unsafe_allow_html=True)


def _render_timeline(st: Any, screen: GameScreenView) -> None:
    st.markdown(timeline_header_html(), unsafe_allow_html=True)
    if not screen.timeline:
        st.info("まだ表示できる出来事がありません。")
        return
    st.markdown(timeline_html(screen.timeline), unsafe_allow_html=True)


def _render_action_panel(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    screen: GameScreenView,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> None:
    st.markdown(hand_panel_html(screen.hand_panel), unsafe_allow_html=True)
    if screen.observation is not None:
        st.markdown("#### あなたの役職")
        st.info(f"{screen.observation.role}。あなただけに見えている情報です。")
        st.markdown("#### 見えている情報")
        if screen.observation.known_role_lines:
            for line in screen.observation.known_role_lines:
                st.write(f"- {line}")
        else:
            st.caption("いま表示できる追加情報はありません。")

    if screen.is_completed:
        return

    if screen.can_submit_action:
        _render_action_form(
            st,
            settings=settings,
            api_url=api_url,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
            screen=screen,
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
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )


def _render_action_form(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    game_id: str,
    human_player_id: str,
    control_token: str,
    screen: GameScreenView,
) -> None:
    if screen.observation is None:
        return

    st.divider()
    st.markdown("#### できる行動")
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

    target_id = None
    if selected_action.requires_target:
        if candidates:
            selected_target = st.selectbox("対象を選ぶ", candidates)
            target_id = str(selected_target) if selected_target else None
        else:
            st.warning("選べる対象がありません。")

    message = None
    if selected_action.requires_message:
        message = st.text_area(
            "発言内容",
            key=KEY_MESSAGE,
            placeholder="ここに発言を入力...",
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
                game_id=game_id,
                human_player_id=human_player_id,
                control_token=control_token,
                action_type=selected_action.action_type,
                target_id=target_id,
                message=str(message).strip() if message else None,
            )
        except AppError as exc:
            st.error(exc.detail)
            return
        st.session_state[KEY_MESSAGE] = ""
        st.success("入力を送信しました。")
        st.rerun()


def _run_until_input(
    st: Any,
    *,
    settings: AppSettings,
    api_url: str,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> None:
    try:
        result = advance_until_input(
            api_url=api_url,
            settings=settings,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )
    except AppError as exc:
        st.error(exc.detail)
        return
    if result.completed or result.reached_input:
        st.rerun()
        return
    if result.hit_limit:
        st.warning("進行の上限に達しました。現在の状態を確認してください。")


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
