"""Deterministic canonical checksums and replay integrity verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import ValidationError

from werewolf_agent.domain import GameState
from werewolf_agent.usecase.models import ReplayVerificationResult
from werewolf_agent.usecase.projections import public_state_payload_from_snapshot


class ReplayRepository(Protocol):
    """Persistence data needed for private replay verification."""

    def replay_records(self, game_id: str) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        """Return checksum-bearing command, event, and state records."""


def checksum_payload(payload: Any) -> str:
    """Return a stable SHA-256 checksum for JSON-compatible data."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_replay(game_id: str, repository: ReplayRepository) -> ReplayVerificationResult:
    """Verify checksums, version continuity, and rebuilt public projections."""
    records = repository.replay_records(game_id)
    checked_versions: set[int] = set()
    for stream in ("commands", "events", "states"):
        for record in records.get(stream, ()):
            version = int(record["version"])
            checked_versions.add(version)
            expected = str(record["checksum"])
            actual = checksum_payload(record["payload"])
            if expected != actual:
                return ReplayVerificationResult(
                    game_id=game_id,
                    valid=False,
                    checked_versions=len(checked_versions),
                    first_mismatch_version=version,
                    expected_checksum=expected,
                    actual_checksum=actual,
                )
    state_records = list(records.get("states", ()))
    state_versions = [int(record["version"]) for record in state_records]
    expected_versions = list(range(1, max(state_versions, default=0) + 1))
    if state_versions != expected_versions:
        return _structural_mismatch(
            game_id,
            checked_versions,
            _first_sequence_mismatch(state_versions, expected_versions),
            expected="contiguous state versions",
            actual=",".join(str(version) for version in state_versions),
        )
    command_versions = [int(record["version"]) for record in records.get("commands", ())]
    if command_versions != state_versions:
        return _structural_mismatch(
            game_id,
            checked_versions,
            _first_sequence_mismatch(command_versions, state_versions),
            expected="one accepted command per state version",
            actual=",".join(str(version) for version in command_versions),
        )
    event_records = list(records.get("events", ()))
    event_sequences = [int(record["sequence"]) for record in event_records]
    expected_event_sequences = list(range(1, len(event_sequences) + 1))
    if event_sequences != expected_event_sequences:
        mismatch_index = _first_sequence_mismatch(event_sequences, expected_event_sequences)
        mismatch_version = next(
            (
                int(record["version"])
                for record in event_records
                if int(record["sequence"]) >= mismatch_index
            ),
            1,
        )
        return _structural_mismatch(
            game_id,
            checked_versions,
            mismatch_version,
            expected="contiguous event sequence",
            actual=",".join(str(sequence) for sequence in event_sequences),
        )
    for record in event_records:
        version = int(record["version"])
        if version not in set(state_versions):
            return _structural_mismatch(
                game_id,
                checked_versions,
                version,
                expected="event version with a persisted state",
                actual=str(version),
            )
    state_events = [
        record for record in event_records if record.get("event_type") == "state_committed"
    ]
    state_events_by_version = {int(record["version"]): record for record in state_events}
    if len(state_events) != len(state_events_by_version):
        return _structural_mismatch(
            game_id,
            checked_versions,
            min((int(record["version"]) for record in state_events), default=1),
            expected="one state event per version",
            actual="duplicate state event",
        )
    for state_record in state_records:
        version = int(state_record["version"])
        state_event = state_events_by_version.get(version)
        if state_event is None:
            return _structural_mismatch(
                game_id,
                checked_versions,
                version,
                expected="state_committed event",
                actual="missing state event",
            )
        if checksum_payload(state_event["payload"]) != checksum_payload(state_record["payload"]):
            return ReplayVerificationResult(
                game_id=game_id,
                valid=False,
                checked_versions=len(checked_versions),
                first_mismatch_version=version,
                expected_checksum=checksum_payload(state_record["payload"]),
                actual_checksum=checksum_payload(state_event["payload"]),
            )
    for record in state_records:
        mismatch = _verify_public_projection(
            game_id,
            state_events_by_version[int(record["version"])],
            checked_versions,
        )
        if mismatch is not None:
            return mismatch
    return ReplayVerificationResult(
        game_id=game_id,
        valid=True,
        checked_versions=len(checked_versions),
    )


def _verify_public_projection(
    game_id: str,
    record: Mapping[str, Any],
    checked_versions: set[int],
) -> ReplayVerificationResult | None:
    version = int(record["version"])
    payload = record["payload"]
    if not isinstance(payload, Mapping):
        return _structural_mismatch(
            game_id,
            checked_versions,
            version,
            expected="state payload object",
            actual=type(payload).__name__,
        )
    private_state = payload.get("private_state")
    public_state = payload.get("public_state")
    if not isinstance(private_state, Mapping) or not isinstance(public_state, Mapping):
        return _structural_mismatch(
            game_id,
            checked_versions,
            version,
            expected="private and public state objects",
            actual="invalid state payload",
        )
    try:
        snapshot = GameState.model_validate(private_state)
        rebuilt = public_state_payload_from_snapshot(
            snapshot,
            game_id=game_id,
            version=version,
            seed=_optional_int(public_state.get("seed")),
            created_at=public_state.get("created_at"),
            scenario_id=_optional_text(public_state.get("scenario_id")),
            scenario_name=_optional_text(public_state.get("scenario_name")),
            narration_mode=str(public_state.get("narration_mode") or "standard"),
        )
    except (TypeError, ValueError, ValidationError):
        return _structural_mismatch(
            game_id,
            checked_versions,
            version,
            expected="valid domain snapshot",
            actual="invalid private state",
        )
    expected_checksum = checksum_payload(public_state)
    actual_checksum = checksum_payload(rebuilt)
    if expected_checksum == actual_checksum:
        return None
    return ReplayVerificationResult(
        game_id=game_id,
        valid=False,
        checked_versions=len(checked_versions),
        first_mismatch_version=version,
        expected_checksum=expected_checksum,
        actual_checksum=actual_checksum,
    )


def _first_sequence_mismatch(actual: list[int], expected: list[int]) -> int:
    for actual_version, expected_version in zip(actual, expected, strict=False):
        if actual_version != expected_version:
            return min(actual_version, expected_version)
    if len(actual) < len(expected):
        return expected[len(actual)]
    if len(actual) > len(expected):
        return actual[len(expected)]
    return 1


def _structural_mismatch(
    game_id: str,
    checked_versions: set[int],
    version: int,
    *,
    expected: str,
    actual: str,
) -> ReplayVerificationResult:
    return ReplayVerificationResult(
        game_id=game_id,
        valid=False,
        checked_versions=len(checked_versions),
        first_mismatch_version=max(version, 1),
        expected_checksum=checksum_payload(expected),
        actual_checksum=checksum_payload(actual),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


__all__ = ["ReplayRepository", "checksum_payload", "verify_replay"]
