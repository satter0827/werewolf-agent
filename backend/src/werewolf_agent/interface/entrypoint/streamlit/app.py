"""Playable Streamlit entry point for one human player."""

from __future__ import annotations

import importlib
from typing import Any, cast

from werewolf_agent.commons.configuration import AppSettings, get_settings
from werewolf_agent.contracts import AppError
from werewolf_agent.contracts.schemas import (
    PrivateObservationResponse,
    PublicGameRunSummary,
    PublicGameState,
    SubmitPlayerActionRequest,
)
from werewolf_agent.interface.entrypoint.streamlit.icons import action_label
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
    GameScreenView,
    build_game_screen_view,
)
from werewolf_agent.interface.shared import workflows
from werewolf_agent.interface.shared.api_client import GameApiClient, build_game_api_client
from werewolf_agent.interface.shared.game_requests import build_create_game_request


def main() -> None:
    """Render the Streamlit application."""
    st = _streamlit()
    settings = get_settings()
    st.set_page_config(page_title=settings.streamlit_page_title, page_icon="🐺", layout="wide")
    st.markdown(STREAMLIT_CSS, unsafe_allow_html=True)

    api_url = _render_sidebar(st, settings)
    client = build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)
    game_id = text_value(st.session_state, KEY_GAME_ID)
    human_player_id = text_value(st.session_state, KEY_HUMAN_PLAYER_ID, "player-1")
    control_token = text_value(st.session_state, KEY_CONTROL_TOKEN)

    if not game_id:
        _render_empty_state(st)
        return

    try:
        state = workflows.get_game(client, game_id).state
        turns = workflows.list_turns(client, game_id, limit=settings.streamlit_turn_limit).turns
        observation = _load_observation(
            client,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )
    except AppError as exc:
        st.error(exc.detail)
        return

    screen = build_game_screen_view(
        state=state,
        turns=turns,
        observation=observation,
        human_player_id=human_player_id,
    )
    _render_status_bar(st, screen)
    center, right = st.columns([2.15, 1], gap="medium")
    with center:
        _render_game_table(st, screen)
        _render_timeline(st, screen)
    with right:
        _render_action_panel(
            st,
            client=client,
            settings=settings,
            state=state,
            screen=screen,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )


def _render_sidebar(st: Any, settings: AppSettings) -> str:
    st.sidebar.title("🐺 Werewolf Agent")
    st.sidebar.caption("プレイ")
    st.sidebar.divider()
    st.sidebar.subheader("API 接続")
    default_api_url = text_value(
        st.session_state,
        KEY_API_URL,
        settings.streamlit_resolved_api_url,
    )
    api_url = st.sidebar.text_input("API Base URL", value=default_api_url)
    st.session_state[KEY_API_URL] = api_url
    if st.sidebar.button("接続を確認", use_container_width=True):
        try:
            workflows.check_health(
                build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)
            )
        except AppError as exc:
            st.sidebar.error(exc.detail)
        else:
            st.sidebar.success("接続済み")

    st.sidebar.divider()
    st.sidebar.subheader("現在のゲーム")
    _render_recent_games(st, settings=settings, api_url=str(api_url))

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
        seed_text = st.text_input("シード", value="1")
        human_player_id = st.selectbox(
            "あなたのプレイヤー",
            [f"player-{index}" for index in range(1, int(player_count) + 1)],
            index=0,
        )
        submitted = st.form_submit_button("ゲームを始める", use_container_width=True)
    if submitted:
        _create_game(
            st,
            settings=settings,
            api_url=api_url,
            player_count=int(player_count),
            seed_text=seed_text,
            human_player_id=str(human_player_id),
        )

    st.sidebar.divider()
    st.sidebar.subheader("ゲームを再開")
    with st.sidebar.form("resume-game"):
        game_id = st.text_input("ゲーム ID", value=text_value(st.session_state, KEY_GAME_ID))
        human_player = st.text_input(
            "プレイヤー ID",
            value=text_value(st.session_state, KEY_HUMAN_PLAYER_ID, "player-1"),
        )
        token = st.text_input(
            "操作用 token",
            value=text_value(st.session_state, KEY_CONTROL_TOKEN),
            type="password",
        )
        resumed = st.form_submit_button("再開する", use_container_width=True)
    if resumed and game_id and human_player and token:
        set_game_session(
            st.session_state,
            game_id=game_id,
            human_player_id=human_player,
            control_token=token,
        )
        st.rerun()

    if st.sidebar.button("ゲーム選択をクリア", use_container_width=True):
        clear_game_session(st.session_state)
        st.rerun()

    return str(api_url)


def _render_recent_games(st: Any, *, settings: AppSettings, api_url: str) -> None:
    current_game_id = text_value(st.session_state, KEY_GAME_ID)
    current_human_player = text_value(st.session_state, KEY_HUMAN_PLAYER_ID, "player-1")
    if current_game_id:
        st.sidebar.caption(f"選択中: {current_game_id}")
    try:
        client = build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)
        runs = workflows.list_games(client, limit=settings.streamlit_run_limit).runs
    except AppError:
        st.sidebar.caption("ゲーム一覧は API 接続後に表示されます。")
        return
    if not runs:
        st.sidebar.caption("まだゲームがありません。")
        return

    option_labels = [_game_run_option(run) for run in runs]
    selected_label = st.sidebar.selectbox(
        "最近のゲーム",
        option_labels,
        label_visibility="collapsed",
    )
    selected_run = runs[option_labels.index(selected_label)]
    human_player = st.sidebar.text_input("操作するプレイヤー", value=current_human_player)
    token = st.sidebar.text_input(
        "操作用 token",
        value=text_value(st.session_state, KEY_CONTROL_TOKEN),
        type="password",
    )
    if st.sidebar.button("このゲームを開く", use_container_width=True):
        set_game_session(
            st.session_state,
            game_id=selected_run.game_id,
            human_player_id=human_player,
            control_token=token,
        )
        st.rerun()


def _game_run_option(run: PublicGameRunSummary) -> str:
    status = "終了" if run.status == "completed" else "進行中"
    return f"{status} / Day {run.day} / {run.game_id}"


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
        seed = int(seed_text) if seed_text.strip() else None
        request = build_create_game_request(
            players=player_count,
            seed=seed,
            human_player=human_player_id,
            role_count_entries=[],
            tie_break_policy="no_elimination",
            day_speech_turns=1,
            allow_self_vote=False,
            default_player_count=settings.game_default_player_count,
        )
        client = build_game_api_client(api_url, timeout=settings.streamlit_http_timeout_seconds)
        created = workflows.create_game(client, request)
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
    st.markdown("## Werewolf Agent")
    st.info("サイドバーで API 接続を確認し、新しいゲームを始めてください。")


def _load_observation(
    client: GameApiClient,
    *,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> PrivateObservationResponse | None:
    if not game_id or not human_player_id or not control_token:
        return None
    return workflows.get_private_observation(
        client,
        game_id,
        human_player_id,
        control_token=control_token,
    )


def _render_status_bar(st: Any, screen: GameScreenView) -> None:
    columns = st.columns(6)
    values = [
        ("現在のフェーズ", f"{screen.day_label} {screen.phase_label}"),
        ("生存プレイヤー", screen.alive_label),
        ("経過ターン", screen.turn_label),
        ("現在の手番", screen.current_turn_title),
        ("状態", screen.status_label),
        ("勝利", screen.winner_label),
    ]
    for column, (label, value) in zip(columns, values, strict=True):
        column.markdown(
            f'<div class="wa-status"><div class="wa-muted">{label}</div><b>{value}</b></div>',
            unsafe_allow_html=True,
        )


def _render_game_table(st: Any, screen: GameScreenView) -> None:
    st.markdown("### ゲーム卓")
    st.caption("プレイヤーの現在状態")
    columns = st.columns(len(screen.seats))
    for column, seat in zip(columns, screen.seats, strict=True):
        classes = ["wa-seat"]
        if seat.is_human:
            classes.append("wa-seat-human")
        if not seat.is_alive:
            classes.append("wa-seat-dead")
        chip_class = "wa-chip" if seat.is_alive else "wa-chip wa-chip-danger"
        column.markdown(
            f"""
            <div class="{" ".join(classes)}">
                <div style="font-size:26px;">👤</div>
                <b>{seat.player_id}</b>
                <div class="{chip_class}">{seat.status}</div>
                <div class="wa-muted">{seat.activity}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_timeline(st: Any, screen: GameScreenView) -> None:
    st.markdown("### これまでの流れ")
    st.caption("公開された出来事を時系列で表示します。非公開情報は出ません。")
    if not screen.timeline:
        st.info("まだ表示できる出来事がありません。")
        return

    st.markdown('<div class="wa-timeline">', unsafe_allow_html=True)
    for item in screen.timeline:
        st.markdown(
            f"""
            <div class="wa-timeline-item wa-timeline-item-{item.tone}">
                <div class="wa-muted">{item.day_label} / {item.time_text}</div>
                <b>{item.icon} {item.title}</b>
                <div>{item.detail}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_action_panel(
    st: Any,
    *,
    client: GameApiClient,
    settings: AppSettings,
    state: PublicGameState,
    screen: GameScreenView,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> None:
    st.markdown("### あなたの手番")
    st.markdown(
        f"""
        <div class="wa-primary-note">
            <b>{screen.current_turn_title}</b>
            <div>{screen.current_turn_detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if screen.observation is not None:
        st.markdown("#### あなたの役職")
        st.info(f"{screen.observation.role}。他のプレイヤーには表示されません。")
        if screen.observation.known_role_lines:
            st.markdown("#### 見えている情報")
            for line in screen.observation.known_role_lines:
                st.write(f"- {line}")

    if state.status == "completed":
        return

    if screen.observation is not None and screen.observation.available_actions:
        _render_action_form(
            st,
            client=client,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
            screen=screen,
        )
        return

    st.divider()
    st.markdown("#### 現在の手番")
    st.caption("次の入力が必要な場面まで進められます。")
    if st.button("次の入力待ちまで進める", type="primary", use_container_width=True):
        _run_until_input(
            st,
            client=client,
            settings=settings,
            game_id=game_id,
            human_player_id=human_player_id,
            control_token=control_token,
        )


def _render_action_form(
    st: Any,
    *,
    client: GameApiClient,
    game_id: str,
    human_player_id: str,
    control_token: str,
    screen: GameScreenView,
) -> None:
    if screen.observation is None:
        return
    st.divider()
    st.markdown("#### できる行動")
    actions = screen.observation.available_actions
    selected_label = st.radio(
        "行動",
        [action_label(action) for action in actions],
        horizontal=True,
        label_visibility="collapsed",
    )
    selected_action = actions[[action_label(action) for action in actions].index(selected_label)]
    candidates = screen.observation.target_candidates.get(selected_action, [])
    target_id = None
    if candidates:
        target_id = st.selectbox("対象を選ぶ", candidates)

    message = None
    if selected_action == "speech":
        message = st.text_area(
            "発言内容",
            key=KEY_MESSAGE,
            placeholder="ここに発言を入力...",
            max_chars=200,
        )

    send_label = f"{action_label(selected_action)}を送信"
    if st.button(send_label, type="primary", use_container_width=True):
        if selected_action == "speech" and not str(message or "").strip():
            st.warning("発言内容を入力してください。")
            return
        if selected_action not in {"speech", "pass"} and not target_id:
            st.warning("対象を選んでください。")
            return
        try:
            workflows.submit_player_action(
                client,
                game_id,
                human_player_id,
                SubmitPlayerActionRequest(
                    type=cast(Any, selected_action),
                    target_id=str(target_id) if target_id else None,
                    message=str(message).strip() if message else None,
                ),
                control_token=control_token,
            )
        except AppError as exc:
            st.error(exc.detail)
            return
        st.session_state[KEY_MESSAGE] = ""
        st.success("行動を送信しました。")
        st.rerun()


def _run_until_input(
    st: Any,
    *,
    client: GameApiClient,
    settings: AppSettings,
    game_id: str,
    human_player_id: str,
    control_token: str,
) -> None:
    try:
        for _ in range(settings.streamlit_max_auto_steps):
            current = workflows.get_game(client, game_id).state
            if current.status == "completed":
                st.rerun()
                return
            observation = _load_observation(
                client,
                game_id=game_id,
                human_player_id=human_player_id,
                control_token=control_token,
            )
            if observation is not None and observation.observation.get("available_actions"):
                st.rerun()
                return
            workflows.step_game(client, game_id)
    except AppError as exc:
        st.error(exc.detail)
        return
    st.warning("自動進行の上限に達しました。現在の状態を確認してください。")


def _streamlit() -> Any:
    return importlib.import_module("streamlit")


main()
