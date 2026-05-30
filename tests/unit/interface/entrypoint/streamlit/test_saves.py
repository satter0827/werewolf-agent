from datetime import UTC, datetime

from werewolf_agent.contracts.schemas import (
    GameRunResponse,
    PublicGameRunSummary,
    PublicGameState,
    PublicPlayerState,
)
from werewolf_agent.interface.entrypoint.streamlit.saves import (
    SaveSlot,
    build_saved_game_options,
    create_save_slot,
    load_save_slots,
    upsert_save_slot,
)


def _state() -> PublicGameState:
    return PublicGameState(
        game_id="game-secret-1",
        status="running",
        phase="day_discussion",
        day=2,
        version=3,
        seed=1,
        players=[
            PublicPlayerState(id="player-1", name="P1", alive=True, status="alive"),
            PublicPlayerState(id="player-2", name="P2", alive=True, status="alive"),
        ],
        alive_player_ids=["player-1", "player-2"],
        eliminated_player_ids=[],
        summary={"alive_count": 2},
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, 12, 34, tzinfo=UTC),
    )


def _run() -> PublicGameRunSummary:
    return PublicGameRunSummary(
        game_id="game-secret-1",
        status="running",
        phase="day_discussion",
        day=2,
        version=3,
        seed=1,
        player_count=2,
        alive_count=2,
        step_count=3,
        turn_count=4,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, 12, 35, tzinfo=UTC),
    )


def test_new_game_save_slot_can_be_loaded_as_playable(tmp_path) -> None:
    save_file = tmp_path / "saves.json"
    response = GameRunResponse(
        game_id="game-secret-1",
        state=_state(),
        control_tokens={"player-1": "token-secret"},
    )
    slot = create_save_slot(
        response,
        human_player_id="player-1",
    )

    upsert_save_slot(save_file, slot)

    loaded = load_save_slots(save_file)
    assert loaded == [slot]
    saved_text = save_file.read_text(encoding="utf-8")
    assert "control_token" not in saved_text
    assert "token-secret" not in saved_text

    option = build_saved_game_options(
        loaded,
        [_run()],
        control_tokens={slot.slot_id: "token-secret"},
    )[0]
    assert option.mode == "playable"
    assert option.game_id == "game-secret-1"
    assert option.human_player_id == "player-1"
    assert option.control_token == "token-secret"
    assert "プレイ可能" in option.label
    assert "game-secret-1" not in option.label
    assert "player-1" not in option.label
    assert "token-secret" not in option.label


def test_saved_slot_without_session_token_becomes_observer_option(tmp_path) -> None:
    save_file = tmp_path / "saves.json"
    slot = create_save_slot(
        GameRunResponse(game_id="game-secret-1", state=_state()),
        human_player_id="player-1",
    )
    upsert_save_slot(save_file, slot)

    option = build_saved_game_options(load_save_slots(save_file), [_run()])[0]

    assert option.mode == "observer"
    assert option.human_player_id is None
    assert option.control_token == ""
    assert "観戦のみ" in option.label


def test_api_run_without_save_slot_becomes_observer_option() -> None:
    option = build_saved_game_options([], [_run()])[0]

    assert option.mode == "observer"
    assert option.human_player_id is None
    assert option.control_token == ""
    assert "観戦のみ" in option.label
    assert "game-secret-1" not in option.label


def test_invalid_save_file_is_ignored(tmp_path) -> None:
    save_file = tmp_path / "saves.json"
    save_file.write_text('{"version": 0, "slots": "old"}', encoding="utf-8")

    assert load_save_slots(save_file) == []

    save_file.write_text("{not-json", encoding="utf-8")
    assert load_save_slots(save_file) == []


def test_token_bearing_save_slot_is_ignored(tmp_path) -> None:
    save_file = tmp_path / "saves.json"
    save_file.write_text(
        """
        {
          "version": 2,
          "slots": [
            {
              "slot_id": "slot-1",
              "game_id": "game-secret-1",
              "human_player_id": "player-1",
              "control_token": "token-secret",
              "status": "running",
              "phase": "day_discussion",
              "day": 1,
              "player_count": 2,
              "alive_count": 2,
              "created_at": null,
              "updated_at": null
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    assert load_save_slots(save_file) == []


def test_save_slot_refreshes_from_public_state() -> None:
    slot = SaveSlot(
        slot_id="slot-1",
        game_id="game-secret-1",
        human_player_id="player-1",
        status="running",
        phase="night",
        day=1,
        player_count=2,
        alive_count=2,
        created_at=None,
        updated_at=None,
    )

    refreshed = slot.with_state(_state())

    assert refreshed.phase == "day_discussion"
    assert refreshed.day == 2
    assert refreshed.updated_at == datetime(2026, 1, 1, 12, 34, tzinfo=UTC)
