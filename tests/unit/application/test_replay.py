from collections.abc import Mapping, Sequence

from werewolf_agent.application.replay import checksum_payload, verify_replay


class EmptyReplayRepository:
    def replay_records(self, _game_id: str) -> Mapping[str, Sequence[Mapping[str, object]]]:
        return {"commands": (), "events": (), "states": ()}


def test_replay_rejects_missing_v2_genesis() -> None:
    result = verify_replay("game-1", EmptyReplayRepository())

    assert result.valid is False
    assert result.first_mismatch_version == 1


def test_checksum_is_canonical_for_mapping_order() -> None:
    assert checksum_payload({"a": 1, "b": 2}) == checksum_payload({"b": 2, "a": 1})
