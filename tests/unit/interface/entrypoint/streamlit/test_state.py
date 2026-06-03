from werewolf_agent.interface.entrypoint.streamlit.state import (
    KEY_AUTO_ADVANCE_GAME_ID,
    KEY_AUTO_ADVANCE_LAST_STEP_AT,
    KEY_AUTO_ADVANCE_NOTICE,
    KEY_AUTO_ADVANCE_RUNNING,
    KEY_AUTO_ADVANCE_STEPS,
    KEY_MANUAL_PLAYER_TOKENS,
    auto_advance_state,
    consume_auto_advance_notice,
    manual_player_tokens_by_slot,
    pause_auto_advance,
    record_auto_advance_step,
    remember_manual_player_token,
    start_auto_advance,
    sync_auto_advance_game,
)


def test_manual_player_tokens_are_kept_in_session_state_only() -> None:
    session: dict[str, object] = {}

    remember_manual_player_token(
        session,
        slot_id="slot-1",
        manual_token="token-secret",
    )

    assert session[KEY_MANUAL_PLAYER_TOKENS] == {"slot-1": "token-secret"}
    assert manual_player_tokens_by_slot(session) == {"slot-1": "token-secret"}


def test_manual_player_token_session_helper_ignores_empty_or_invalid_values() -> None:
    session: dict[str, object] = {KEY_MANUAL_PLAYER_TOKENS: "not-a-dict"}

    assert manual_player_tokens_by_slot(session) == {}


def test_auto_advance_state_tracks_start_pause_and_step_count() -> None:
    session: dict[str, object] = {}

    start_auto_advance(session, "game-1")
    record_auto_advance_step(session, game_id="game-1", now=12.5)
    pause_auto_advance(session, notice="stopped")

    state = auto_advance_state(session, "game-1")
    assert state.game_id == "game-1"
    assert state.running is False
    assert state.steps == 1
    assert state.last_step_at == 12.5
    assert consume_auto_advance_notice(session) == "stopped"
    assert KEY_AUTO_ADVANCE_NOTICE not in session


def test_auto_advance_resets_when_visible_game_changes() -> None:
    session: dict[str, object] = {}
    start_auto_advance(session, "game-1")
    record_auto_advance_step(session, game_id="game-1", now=1.0)

    sync_auto_advance_game(session, "game-2")

    assert session[KEY_AUTO_ADVANCE_GAME_ID] == "game-2"
    assert session[KEY_AUTO_ADVANCE_RUNNING] is False
    assert session[KEY_AUTO_ADVANCE_STEPS] == 0
    assert session[KEY_AUTO_ADVANCE_LAST_STEP_AT] == 0.0
    assert auto_advance_state(session, "game-1").running is False

    remember_manual_player_token(session, slot_id="", manual_token="token-secret")
    remember_manual_player_token(session, slot_id="slot-1", manual_token="")

    assert manual_player_tokens_by_slot(session) == {}
