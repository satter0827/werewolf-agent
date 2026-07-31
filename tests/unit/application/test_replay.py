from collections.abc import Mapping, Sequence

import pytest

from werewolf_agent.application.replay import verify_replay
from werewolf_agent.setup import checksum_payload


class EmptyReplayRepository:
    def replay_records(self, _game_id: str) -> Mapping[str, Sequence[Mapping[str, object]]]:
        return {"commands": (), "events": (), "states": ()}


class StaticReplayRepository:
    def __init__(self, records: Mapping[str, Sequence[Mapping[str, object]]]) -> None:
        self._records = records

    def replay_records(self, _game_id: str) -> Mapping[str, Sequence[Mapping[str, object]]]:
        return self._records


def test_replay_rejects_missing_v2_genesis() -> None:
    result = verify_replay("game-1", EmptyReplayRepository())

    assert result.valid is False
    assert result.first_mismatch_version == 1


def test_checksum_is_canonical_for_mapping_order() -> None:
    assert checksum_payload({"a": 1, "b": 2}) == checksum_payload({"b": 2, "a": 1})


@pytest.mark.parametrize("stream", ("commands", "events", "states"))
def test_replay_detects_each_tampered_checksum_before_reexecution(stream: str) -> None:
    payload = {"nested": {"value": 1}, "items": ["a", "b"]}
    repository = StaticReplayRepository(
        {
            "commands": (),
            "events": (),
            "states": (),
            stream: (
                {
                    "version": 2,
                    "payload": payload,
                    "checksum": "tampered",
                },
            ),
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 2
    assert result.comparison_target == stream
    assert result.expected_checksum == "tampered"
    assert result.actual_checksum == checksum_payload(payload)
