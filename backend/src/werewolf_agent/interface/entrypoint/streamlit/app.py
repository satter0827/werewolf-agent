"""Streamlit console for the public Werewolf Agent API."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar, cast

from pydantic import ValidationError

from werewolf_agent.commons.configuration import (
    AppSettings,
    configure_interface_logging,
    get_settings,
    settings_error_detail,
)
from werewolf_agent.commons.shared.messages import (
    LOG_STREAMLIT_ACTION_SUBMITTED,
    LOG_STREAMLIT_APPLICATION_ERROR_HANDLED,
    LOG_STREAMLIT_GAME_CREATED,
    LOG_STREAMLIT_GAME_STEPPED,
    LOG_STREAMLIT_REFRESHED,
)
from werewolf_agent.contracts import AppError, ConfigError
from werewolf_agent.contracts.schemas import (
    GameResponse,
    GameRunsResponse,
    PrivateObservationResponse,
    PublicGameState,
    SubmitPlayerActionRequest,
)
from werewolf_agent.interface.entrypoint.streamlit.i18n import (
    LANGUAGE_NAMES,
    Language,
    normalize_language,
    text,
)
from werewolf_agent.interface.shared import workflows
from werewolf_agent.interface.shared.api_client import GameApiClient, build_game_api_client
from werewolf_agent.interface.shared.game_requests import build_create_game_request

st = cast(Any, importlib.import_module("streamlit"))
logger = logging.getLogger(__name__)
T = TypeVar("T")
ClientFactory = Callable[[str, float], GameApiClient]


def default_client_factory(api_url: str, timeout: float) -> GameApiClient:
    """Build the default public API client."""
    return build_game_api_client(api_url, timeout=timeout)


def render_app(
    *,
    settings: AppSettings | None = None,
    client_factory: ClientFactory = default_client_factory,
) -> None:
    """Render the Streamlit application."""
    try:
        loaded_settings = settings or get_settings()
        configure_interface_logging(
            loaded_settings,
            service_name=loaded_settings.streamlit_service_name,
        )
    except ValidationError as exc:
        _render_configuration_error(ConfigError(settings_error_detail(exc)))
        return

    st.set_page_config(page_title=loaded_settings.streamlit_page_title, layout="wide")
    _inject_css()
    _init_session(loaded_settings)

    language = _render_language_control(loaded_settings)
    api_url = _render_api_url_control(loaded_settings, language)
    client = client_factory(api_url, loaded_settings.streamlit_http_timeout_seconds)

    st.title(text(language, "main_title"))
    runs = _load_runs(client, loaded_settings, language)
    active_game_id = _render_sidebar(
        client=client,
        settings=loaded_settings,
        language=language,
        runs=runs,
        api_url=api_url,
    )
    _render_main_console(
        client=client,
        settings=loaded_settings,
        language=language,
        active_game_id=active_game_id,
    )


def _render_configuration_error(error: AppError) -> None:
    st.set_page_config(page_title="Werewolf Agent", layout="wide")
    st.error(error.detail)


def _init_session(settings: AppSettings) -> None:
    defaults: dict[str, object] = {
        "active_game_id": "",
        "control_tokens": {},
        "human_player_id": "player-1",
        "language": settings.streamlit_language,
        "last_observation": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_language_control(settings: AppSettings) -> Language:
    configured = normalize_language(
        str(st.session_state.get("language", settings.streamlit_language))
    )
    labels = [LANGUAGE_NAMES["ja"], LANGUAGE_NAMES["en"]]
    label_to_language = {LANGUAGE_NAMES[key]: key for key in LANGUAGE_NAMES}
    selected = st.sidebar.selectbox(
        text(configured, "language"),
        labels,
        index=0 if configured == "ja" else 1,
        key="language_label",
    )
    language = normalize_language(str(label_to_language.get(str(selected), "ja")))
    st.session_state["language"] = language
    return language


def _render_api_url_control(settings: AppSettings, language: Language) -> str:
    st.sidebar.header(text(language, "api_connection"))
    default_api_url = str(st.session_state.get("api_url", settings.streamlit_resolved_api_url))
    api_url = str(st.sidebar.text_input(text(language, "api_url"), value=default_api_url))
    st.session_state["api_url"] = api_url
    return api_url


def _render_sidebar(
    *,
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
    runs: GameRunsResponse | None,
    api_url: str,
) -> str:
    health = _safe_call(language, lambda: workflows.check_health(client))
    if health is None:
        st.sidebar.error(text(language, "connection_failed"))
    else:
        st.sidebar.success(text(language, "connection_ok"))
    logger.debug(
        LOG_STREAMLIT_REFRESHED,
        extra={"api_url": api_url, "has_health": health is not None},
    )

    run_ids = [run.game_id for run in runs.runs] if runs is not None else []
    active_game_id = str(st.session_state.get("active_game_id", ""))
    if active_game_id and active_game_id not in run_ids:
        run_ids.insert(0, active_game_id)
    if run_ids:
        selected = st.sidebar.selectbox(
            text(language, "active_game"),
            run_ids,
            index=run_ids.index(active_game_id) if active_game_id in run_ids else 0,
        )
        active_game_id = str(selected)
        st.session_state["active_game_id"] = active_game_id
    else:
        st.sidebar.info(text(language, "no_active_game"))

    _render_create_game_controls(client=client, settings=settings, language=language)
    _render_refresh_controls(settings=settings, language=language)
    return active_game_id


def _render_create_game_controls(
    *,
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
) -> None:
    st.sidebar.header(text(language, "create_game"))
    players = int(
        st.sidebar.number_input(
            text(language, "players"),
            min_value=settings.game_min_players,
            max_value=settings.game_max_players,
            value=settings.game_default_player_count,
            step=1,
        )
    )
    seed_text = str(st.sidebar.text_input(text(language, "seed"), value="1")).strip()
    seed = int(seed_text) if seed_text else None
    include_human = bool(st.sidebar.checkbox(text(language, "use_human_player"), value=False))
    human_player = None
    if include_human:
        player_options = [f"player-{index}" for index in range(1, players + 1)]
        human_player = str(st.sidebar.selectbox(text(language, "human_player"), player_options))

    if st.sidebar.button(text(language, "create_game"), type="primary"):
        request = build_create_game_request(
            players=players,
            seed=seed,
            human_player=human_player,
            role_count_entries=[],
            tie_break_policy="no_elimination",
            day_speech_turns=1,
            allow_self_vote=False,
            default_player_count=settings.game_default_player_count,
        )
        created = _safe_call(language, lambda: workflows.create_game(client, request))
        if created is None:
            return
        st.session_state["active_game_id"] = created.game_id
        if created.control_tokens:
            control_tokens = _session_control_tokens()
            control_tokens.update(created.control_tokens)
            st.session_state["control_tokens"] = control_tokens
        logger.info(
            LOG_STREAMLIT_GAME_CREATED,
            extra={"game_id": created.game_id, "human_player": human_player},
        )
        st.sidebar.success(text(language, "created_game"))
        st.rerun()


def _render_refresh_controls(*, settings: AppSettings, language: Language) -> None:
    st.sidebar.header(text(language, "refresh_controls"))
    auto_refresh = bool(st.sidebar.checkbox(text(language, "auto_refresh"), value=False))
    if st.sidebar.button(text(language, "manual_refresh")):
        st.rerun()
    if auto_refresh and settings.streamlit_refresh_interval_seconds > 0:
        interval = max(1, int(settings.streamlit_refresh_interval_seconds))
        st.markdown(
            f"<meta http-equiv='refresh' content='{interval}'>",
            unsafe_allow_html=True,
        )


def _render_main_console(
    *,
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
    active_game_id: str,
) -> None:
    if not active_game_id:
        st.info(text(language, "no_active_game"))
        _render_runs_tab_content(None, language)
        return

    game = _safe_call(language, lambda: workflows.get_game(client, active_game_id))
    if game is None:
        return

    _render_status_strip(game.state, language)
    _render_players_and_step(client=client, game=game, language=language)

    timeline_tab, events_tab, action_tab, runs_tab = st.tabs(
        [
            text(language, "timeline"),
            text(language, "events"),
            text(language, "human_action"),
            text(language, "runs"),
        ]
    )
    with timeline_tab:
        _render_timeline_tab(client, settings, language, active_game_id)
    with events_tab:
        _render_events_tab(client, settings, language, active_game_id)
    with action_tab:
        _render_human_action_tab(client, language, game.state)
    with runs_tab:
        _render_runs_tab(client, settings, language)


def _render_status_strip(state: PublicGameState, language: Language) -> None:
    columns = st.columns(6)
    columns[0].metric(text(language, "game_id"), state.game_id)
    columns[1].metric(text(language, "status"), state.status)
    columns[2].metric(text(language, "phase"), state.phase)
    columns[3].metric(text(language, "day"), state.day)
    columns[4].metric(
        text(language, "alive_count"),
        f"{len(state.alive_player_ids)} / {len(state.players)}",
    )
    columns[5].metric(
        text(language, "current_winner"),
        state.winner or text(language, "winner_pending"),
    )


def _render_players_and_step(
    *,
    client: GameApiClient,
    game: GameResponse,
    language: Language,
) -> None:
    st.subheader(text(language, "players"))
    st.dataframe(_player_rows(game.state, language), width="stretch", hide_index=True)
    if st.button(text(language, "step_game"), type="primary"):
        stepped = _safe_call(language, lambda: workflows.step_game(client, game.game_id))
        if stepped is not None:
            logger.info(LOG_STREAMLIT_GAME_STEPPED, extra={"game_id": game.game_id})
            st.success(text(language, "stepped_game"))
            st.rerun()


def _render_timeline_tab(
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
    game_id: str,
) -> None:
    turns = _safe_call(
        language,
        lambda: workflows.list_turns(client, game_id, limit=settings.streamlit_turn_limit),
    )
    if turns is None or not turns.turns:
        st.info(text(language, "timeline_empty"))
        return
    rows = [
        {
            "sequence": turn.sequence,
            "day": turn.day,
            "phase": turn.phase,
            "event_type": turn.event_type,
            "actor_id": turn.actor_id or "",
            "occurred_at": _format_datetime(turn.occurred_at),
        }
        for turn in turns.turns
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_events_tab(
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
    game_id: str,
) -> None:
    events = _safe_call(
        language,
        lambda: workflows.list_events(client, game_id, limit=settings.streamlit_event_limit),
    )
    if events is None or not events.events:
        st.info(text(language, "events_empty"))
        return
    rows = [
        {
            "sequence": event.sequence,
            "day": event.day,
            "phase": event.phase,
            "event_type": event.event_type,
            "actor_id": event.actor_id or "",
            "occurred_at": _format_datetime(event.occurred_at),
        }
        for event in events.events
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_human_action_tab(
    client: GameApiClient,
    language: Language,
    state: PublicGameState,
) -> None:
    st.caption(text(language, "token_help"))
    player_ids = [player.id for player in state.players]
    player_id = str(
        st.selectbox(
            text(language, "player_id"),
            player_ids,
            index=(
                player_ids.index(_session_player_id()) if _session_player_id() in player_ids else 0
            ),
        )
    )
    st.session_state["human_player_id"] = player_id
    token_default = _session_control_tokens().get(player_id, "")
    control_token = str(
        st.text_input(
            text(language, "control_token"),
            value=token_default,
            type="password",
        )
    )
    if control_token:
        control_tokens = _session_control_tokens()
        control_tokens[player_id] = control_token
        st.session_state["control_tokens"] = control_tokens
    if st.button(text(language, "clear_token")):
        control_tokens = _session_control_tokens()
        control_tokens.pop(player_id, None)
        st.session_state["control_tokens"] = control_tokens
        st.session_state["last_observation"] = None
        st.rerun()

    if st.button(text(language, "show_observation")) and control_token:
        observation = _safe_call(
            language,
            lambda: workflows.get_private_observation(
                client,
                state.game_id,
                player_id,
                control_token=control_token,
            ),
        )
        if observation is not None:
            st.session_state["last_observation"] = observation
            st.success(text(language, "observation_loaded"))

    observation = _session_observation()
    if observation is not None:
        st.subheader(text(language, "observation"))
        st.json(observation.observation)
        _render_action_composer(
            client=client,
            language=language,
            state=state,
            player_id=player_id,
            control_token=control_token,
            observation=observation,
        )


def _render_action_composer(
    *,
    client: GameApiClient,
    language: Language,
    state: PublicGameState,
    player_id: str,
    control_token: str,
    observation: PrivateObservationResponse,
) -> None:
    raw_actions = observation.observation.get("available_actions", [])
    actions = [str(action) for action in raw_actions] if isinstance(raw_actions, list) else []
    if not actions:
        return
    action_type = str(st.selectbox(text(language, "action_type"), actions))
    target_id = None
    message = None
    if action_type == "speech":
        message = str(st.text_area(text(language, "action_message"), value=""))
    elif action_type != "pass":
        target_options = [player.id for player in state.players if player.id != player_id]
        if target_options:
            target_id = str(st.selectbox(text(language, "action_target"), target_options))
    reason = str(st.text_area(text(language, "action_reason"), value=""))
    if st.button(text(language, "submit_action"), type="primary") and control_token:
        request = SubmitPlayerActionRequest(
            type=cast(Any, action_type),
            target_id=target_id,
            message=message,
            reason=reason,
        )
        submitted = _safe_call(
            language,
            lambda: workflows.submit_player_action(
                client,
                state.game_id,
                player_id,
                request,
                control_token=control_token,
            ),
        )
        if submitted is not None:
            logger.info(
                LOG_STREAMLIT_ACTION_SUBMITTED,
                extra={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "action_type": action_type,
                },
            )
            st.success(text(language, "action_submitted"))
            st.rerun()


def _render_runs_tab(
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
) -> None:
    runs = _load_runs(client, settings, language)
    _render_runs_tab_content(runs, language)


def _render_runs_tab_content(runs: GameRunsResponse | None, language: Language) -> None:
    st.subheader(text(language, "recent_runs"))
    if runs is None or not runs.runs:
        st.info(text(language, "runs_empty"))
        return
    rows = [
        {
            "game_id": run.game_id,
            "status": run.status,
            "phase": run.phase,
            "day": run.day,
            "winner": run.winner or "",
            "players": run.player_count,
            "alive": run.alive_count,
            "updated_at": _format_datetime(run.updated_at),
        }
        for run in runs.runs
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def _load_runs(
    client: GameApiClient,
    settings: AppSettings,
    language: Language,
) -> GameRunsResponse | None:
    return _safe_call(
        language,
        lambda: workflows.list_games(client, limit=settings.streamlit_run_limit),
    )


def _safe_call(language: Language, action: Callable[[], T]) -> T | None:
    try:
        return action()
    except AppError as exc:
        logger.warning(LOG_STREAMLIT_APPLICATION_ERROR_HANDLED, extra=exc.log_extra())
        st.error(exc.detail or text(language, "api_unavailable"))
        return None


def _player_rows(state: PublicGameState, language: Language) -> list[dict[str, object]]:
    return [
        {
            "id": player.id,
            "name": player.name,
            "status": text(language, "alive") if player.alive else text(language, "dead"),
            "alive": player.alive,
            "eliminated_day": player.eliminated_day or "",
            "killed_night": player.killed_night or "",
        }
        for player in state.players
    ]


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _session_control_tokens() -> dict[str, str]:
    raw_tokens = st.session_state.get("control_tokens", {})
    if not isinstance(raw_tokens, dict):
        return {}
    return {str(key): str(value) for key, value in raw_tokens.items()}


def _session_player_id() -> str:
    return str(st.session_state.get("human_player_id", "player-1"))


def _session_observation() -> PrivateObservationResponse | None:
    raw_observation = st.session_state.get("last_observation")
    if isinstance(raw_observation, PrivateObservationResponse):
        return raw_observation
    return None


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; }
        div[data-testid="stMetric"] {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            background: #ffffff;
        }
        .stButton > button[kind="primary"] {
            background: #b11226;
            border-color: #b11226;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    render_app()
