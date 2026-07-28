from werewolf_agent.clients.streamlit.history import SessionGameSelection


def test_session_selection_contains_only_runtime_choices() -> None:
    selection = SessionGameSelection(
        selection_id="selection",
        game_id="game",
        manual_player_id="p1",
        player_count=6,
        seed=7,
        deliberation_level="standard",
    )

    assert selection.manual_player_id == "p1"
    assert not hasattr(selection, "custom_roles")
    assert not hasattr(selection, "character_assignments")
