import json

import pytest
from pydantic import ValidationError

from werewolf_agent.commons import ObservationError
from werewolf_agent.observation.events import (
    GameEvent,
    JsonlEventWriter,
    NullEventSink,
    error_event,
)


def test_game_event_serializes_to_single_json_line() -> None:
    event = GameEvent(
        event_type="phase_started",
        run_id="run-1",
        game_id="game-1",
        phase="day",
        day=1,
        actor_id="player-1",
        visibility="public",
        payload={"message": "昼が始まりました", "api_key": "secret"},
    )

    payload = json.loads(event.to_json_line())

    assert payload["schema_version"] == "1.0"
    assert payload["event_id"] == str(event.event_id)
    assert payload["event_type"] == "phase_started"
    assert payload["run_id"] == "run-1"
    assert payload["game_id"] == "game-1"
    assert payload["visibility"] == "public"
    assert payload["payload"] == {"message": "昼が始まりました", "api_key": "[REDACTED]"}
    assert isinstance(payload["occurred_at"], str)


def test_jsonl_event_writer_writes_one_event_per_line(tmp_path) -> None:
    path = tmp_path / "game-events.jsonl"
    writer = JsonlEventWriter(path, append=False)

    writer.write(GameEvent(event_type="game_started", payload={"players": 5}))
    writer.write(GameEvent(event_type="vote_cast", actor_id="player-1"))

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "game_started"
    assert json.loads(lines[0])["payload"] == {"players": 5}
    assert json.loads(lines[1])["event_type"] == "vote_cast"


def test_null_event_sink_accepts_events() -> None:
    NullEventSink().write(GameEvent(event_type="ignored"))


def test_error_event_serializes_safe_error_payload() -> None:
    event = error_event(
        ObservationError("Could not write event.", context={"api_key": "secret"}),
        run_id="run-1",
        game_id="game-1",
    )

    payload = json.loads(event.to_json_line())

    assert payload["event_type"] == "error_occurred"
    assert payload["visibility"] == "debug"
    assert payload["payload"] == {
        "code": "observation.write_failed",
        "detail": "Could not write event.",
        "retryable": True,
        "context": {"api_key": "[REDACTED]"},
    }
    assert "stacktrace" not in payload["payload"]


@pytest.mark.parametrize(
    "event",
    [
        {"event_type": ""},
        {"event_type": "phase_started", "day": -1},
        {"event_type": "phase_started", "visibility": "private"},
    ],
)
def test_game_event_rejects_invalid_values(event: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GameEvent(**event)
