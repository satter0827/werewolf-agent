from werewolf_agent.interface.entrypoint.streamlit.state import (
    KEY_CONTROL_TOKENS,
    control_tokens_by_slot,
    remember_control_token,
)


def test_control_tokens_are_kept_in_session_state_only() -> None:
    session: dict[str, object] = {}

    remember_control_token(
        session,
        slot_id="slot-1",
        control_token="token-secret",
    )

    assert session[KEY_CONTROL_TOKENS] == {"slot-1": "token-secret"}
    assert control_tokens_by_slot(session) == {"slot-1": "token-secret"}


def test_control_token_session_helper_ignores_empty_or_invalid_values() -> None:
    session: dict[str, object] = {KEY_CONTROL_TOKENS: "not-a-dict"}

    assert control_tokens_by_slot(session) == {}

    remember_control_token(session, slot_id="", control_token="token-secret")
    remember_control_token(session, slot_id="slot-1", control_token="")

    assert control_tokens_by_slot(session) == {}
