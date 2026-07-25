from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from werewolf_agent.application.replay import checksum_payload, verify_replay


class _ReplayRepository:
    def __init__(self, records: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        self._records = records

    def replay_records(self, _game_id: str) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        return self._records


def _record(version: int, payload: object) -> dict[str, Any]:
    return {
        "version": version,
        "payload": payload,
        "checksum": checksum_payload(payload),
    }


def test_replay_rejects_a_missing_state_version_even_when_checksums_match() -> None:
    repository = _ReplayRepository(
        {
            "commands": [_record(1, {}), _record(3, {})],
            "events": [],
            "states": [_record(1, {}), _record(3, {})],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 2


def test_replay_rejects_a_missing_event_sequence() -> None:
    event_one = {**_record(1, {}), "sequence": 1}
    event_three = {**_record(1, {}), "sequence": 3}
    repository = _ReplayRepository(
        {
            "commands": [_record(1, {})],
            "events": [event_one, event_three],
            "states": [_record(1, {})],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 1


def test_replay_rejects_a_state_event_that_differs_from_the_snapshot() -> None:
    state = _record(1, {"version": 1, "private_state": {}, "public_state": {}})
    state_event = {
        **_record(1, {"version": 1, "private_state": {"changed": True}, "public_state": {}}),
        "sequence": 1,
        "event_type": "state_committed",
    }
    repository = _ReplayRepository(
        {
            "commands": [_record(1, {})],
            "events": [state_event],
            "states": [state],
        }
    )

    result = verify_replay("game-1", repository)

    assert result.valid is False
    assert result.first_mismatch_version == 1
