"""Session-state keys and helpers for the Streamlit entry point."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from werewolf_agent.entrypoint.streamlit.history import SessionGameSelection

KEY_SELECTED_HISTORY_ID = "werewolf_streamlit_selected_history_id"
KEY_ACTIVE_GAME_SELECTION = "werewolf_streamlit_active_game_selection"
KEY_MESSAGE = "werewolf_streamlit_message"
KEY_STREAMLIT_PREFERENCES = "werewolf_streamlit_preferences"
KEY_MANUAL_PLAYER_TOKENS = "werewolf_streamlit_manual_player_tokens"
KEY_AUTO_ADVANCE_GAME_ID = "werewolf_streamlit_auto_advance_game_id"
KEY_AUTO_ADVANCE_RUNNING = "werewolf_streamlit_auto_advance_running"
KEY_AUTO_ADVANCE_STEPS = "werewolf_streamlit_auto_advance_steps"
KEY_AUTO_ADVANCE_LAST_STEP_AT = "werewolf_streamlit_auto_advance_last_step_at"
KEY_AUTO_ADVANCE_NOTICE = "werewolf_streamlit_auto_advance_notice"
KEY_ADVANCE_JOB_GAME_ID = "werewolf_streamlit_advance_job_game_id"
KEY_ADVANCE_JOB_ID = "werewolf_streamlit_advance_job_id"


@dataclass(frozen=True)
class AutoAdvanceState:
    """Current UI-driven auto-advance state."""

    game_id: str
    running: bool
    steps: int
    last_step_at: float


def text_value(session: MutableMapping[str, Any], key: str, default: str = "") -> str:
    """Return a text value from session state."""
    value = session.get(key, default)
    return str(value) if value is not None else default


def remember_selected_history(session: MutableMapping[str, Any], option_id: str) -> None:
    """Store the selected history option id."""
    session[KEY_SELECTED_HISTORY_ID] = option_id


def remember_active_game_selection(
    session: MutableMapping[str, Any],
    selection: SessionGameSelection,
) -> None:
    """Store the session-only playable game selection."""
    session[KEY_ACTIVE_GAME_SELECTION] = selection


def active_game_selection(session: MutableMapping[str, Any]) -> SessionGameSelection | None:
    """Return the session-only playable game selection, if present."""
    value = session.get(KEY_ACTIVE_GAME_SELECTION)
    if not hasattr(value, "selection_id") or not hasattr(value, "game_id"):
        return None
    return cast("SessionGameSelection", value)


def remember_manual_player_token(
    session: MutableMapping[str, Any],
    *,
    slot_id: str,
    manual_token: str,
) -> None:
    """Store one playable token in the current Streamlit session only."""
    slot_id_text = slot_id.strip()
    token_text = manual_token.strip()
    if not slot_id_text or not token_text:
        return
    tokens = manual_player_tokens_by_slot(session)
    tokens[slot_id_text] = token_text
    session[KEY_MANUAL_PLAYER_TOKENS] = tokens


def manual_player_tokens_by_slot(session: MutableMapping[str, Any]) -> dict[str, str]:
    """Return playable tokens held only by the current Streamlit session."""
    value = session.get(KEY_MANUAL_PLAYER_TOKENS)
    if not isinstance(value, dict):
        return {}
    return {
        str(slot_id): str(token)
        for slot_id, token in value.items()
        if str(slot_id).strip() and str(token).strip()
    }


def clear_message(session: MutableMapping[str, Any]) -> None:
    """Clear the current action message."""
    session.pop(KEY_MESSAGE, None)


def sync_auto_advance_game(session: MutableMapping[str, Any], game_id: str) -> None:
    """Reset auto-advance state when the visible game changes."""
    game_id_text = game_id.strip()
    if session.get(KEY_AUTO_ADVANCE_GAME_ID) == game_id_text:
        return
    session[KEY_AUTO_ADVANCE_GAME_ID] = game_id_text
    session[KEY_AUTO_ADVANCE_RUNNING] = False
    session[KEY_AUTO_ADVANCE_STEPS] = 0
    session[KEY_AUTO_ADVANCE_LAST_STEP_AT] = 0.0
    session.pop(KEY_AUTO_ADVANCE_NOTICE, None)
    clear_advance_job(session)


def auto_advance_state(session: MutableMapping[str, Any], game_id: str) -> AutoAdvanceState:
    """Return parsed auto-advance state for the visible game."""
    game_id_text = game_id.strip()
    if session.get(KEY_AUTO_ADVANCE_GAME_ID) != game_id_text:
        return AutoAdvanceState(game_id=game_id_text, running=False, steps=0, last_step_at=0.0)
    return AutoAdvanceState(
        game_id=game_id_text,
        running=bool(session.get(KEY_AUTO_ADVANCE_RUNNING, False)),
        steps=_int_value(session.get(KEY_AUTO_ADVANCE_STEPS), default=0),
        last_step_at=_float_value(session.get(KEY_AUTO_ADVANCE_LAST_STEP_AT), default=0.0),
    )


def start_auto_advance(session: MutableMapping[str, Any], game_id: str) -> None:
    """Start UI-driven auto-advance for one game."""
    game_id_text = game_id.strip()
    session[KEY_AUTO_ADVANCE_GAME_ID] = game_id_text
    session[KEY_AUTO_ADVANCE_RUNNING] = True
    session[KEY_AUTO_ADVANCE_STEPS] = 0
    session[KEY_AUTO_ADVANCE_LAST_STEP_AT] = 0.0
    session.pop(KEY_AUTO_ADVANCE_NOTICE, None)


def pause_auto_advance(session: MutableMapping[str, Any], *, notice: str = "") -> None:
    """Pause UI-driven auto-advance before the next step."""
    session[KEY_AUTO_ADVANCE_RUNNING] = False
    if notice.strip():
        session[KEY_AUTO_ADVANCE_NOTICE] = notice.strip()


def record_auto_advance_step(
    session: MutableMapping[str, Any],
    *,
    game_id: str,
    now: float,
) -> None:
    """Record one completed UI-driven advance step."""
    state = auto_advance_state(session, game_id)
    session[KEY_AUTO_ADVANCE_GAME_ID] = game_id.strip()
    session[KEY_AUTO_ADVANCE_RUNNING] = state.running
    session[KEY_AUTO_ADVANCE_STEPS] = state.steps + 1
    session[KEY_AUTO_ADVANCE_LAST_STEP_AT] = float(now)


def remember_advance_job(
    session: MutableMapping[str, Any],
    *,
    game_id: str,
    job_id: str,
) -> None:
    """Remember the advance job currently being polled by the UI."""
    session[KEY_ADVANCE_JOB_GAME_ID] = game_id.strip()
    session[KEY_ADVANCE_JOB_ID] = job_id.strip()


def advance_job_id(session: MutableMapping[str, Any], game_id: str) -> str:
    """Return the remembered advance job id for one game."""
    if session.get(KEY_ADVANCE_JOB_GAME_ID) != game_id.strip():
        return ""
    return text_value(session, KEY_ADVANCE_JOB_ID)


def clear_advance_job(session: MutableMapping[str, Any]) -> None:
    """Clear the currently remembered advance job."""
    session.pop(KEY_ADVANCE_JOB_GAME_ID, None)
    session.pop(KEY_ADVANCE_JOB_ID, None)


def consume_auto_advance_notice(session: MutableMapping[str, Any]) -> str:
    """Pop and return the latest auto-advance notice."""
    value = session.pop(KEY_AUTO_ADVANCE_NOTICE, "")
    return str(value).strip()


def _int_value(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return default
    return default


def _float_value(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    if isinstance(value, str):
        try:
            return max(float(value), 0.0)
        except ValueError:
            return default
    return default
