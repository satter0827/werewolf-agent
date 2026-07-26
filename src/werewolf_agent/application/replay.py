"""Deterministic canonical checksums and replay integrity verification."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast

from werewolf_agent.application.domain_codec import (
    action_from_data,
    domain_to_data,
    game_setup_from_data,
    game_state_from_data,
)
from werewolf_agent.application.models import ReplayVerificationResult
from werewolf_agent.application.projections import (
    event_to_create,
    public_state_payload_from_snapshot,
)
from werewolf_agent.application.randomness import runtime_seed
from werewolf_agent.application.rules import rule_definition_from_values
from werewolf_agent.application.setup_document import GameSetupDocument
from werewolf_agent.domain import Game, RuleRegistry


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
    """Verify replay data without leaking malformed persistence exceptions."""
    try:
        return _verify_replay_records(game_id, repository)
    except (IndexError, KeyError, TypeError, ValueError):
        return _structural_mismatch(
            game_id,
            set(),
            1,
            expected="complete replay records",
            actual="unsupported replay format",
        )


def _verify_replay_records(
    game_id: str,
    repository: ReplayRepository,
) -> ReplayVerificationResult:
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
                    comparison_target=stream,
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
                comparison_target="state_event",
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
    command_metadata_mismatch = _verify_command_metadata(
        game_id,
        records.get("commands", ()),
        checked_versions,
    )
    if command_metadata_mismatch is not None:
        return command_metadata_mismatch
    execution_mismatch = _verify_execution(
        game_id,
        records,
        checked_versions,
    )
    if execution_mismatch is not None:
        return execution_mismatch
    return ReplayVerificationResult(
        game_id=game_id,
        valid=True,
        checked_versions=len(checked_versions),
    )


def _verify_command_metadata(
    game_id: str,
    commands: Sequence[Mapping[str, Any]],
    checked_versions: set[int],
) -> ReplayVerificationResult | None:
    """Cross-check accepted command metadata against its normalized payload."""
    for command in commands:
        version = int(command["version"])
        try:
            payload = _mapping(command.get("payload"))
            command_type = str(command["command_type"])
            actor_user_id = str(command["actor_user_id"]).strip()
            payload_actor = str(payload["actor_user_id"]).strip()
            expected_version = payload.get("expected_version")
        except (KeyError, TypeError, ValueError):
            return _structural_mismatch(
                game_id,
                checked_versions,
                version,
                expected="complete accepted command metadata",
                actual="unsupported replay format",
                target="command_metadata",
            )
        expected_previous = None if version == 1 else version - 1
        if (
            not actor_user_id
            or actor_user_id != payload_actor
            or payload.get("operation_type") != command_type
            or expected_version != expected_previous
        ):
            return _structural_mismatch(
                game_id,
                checked_versions,
                version,
                expected="consistent actor, command type, and expected version",
                actual="inconsistent accepted command metadata",
                target="command_metadata",
            )
    return None


def _verify_execution(
    game_id: str,
    records: Mapping[str, Sequence[Mapping[str, Any]]],
    checked_versions: set[int],
) -> ReplayVerificationResult | None:
    commands = list(records.get("commands", ()))
    states = {int(record["version"]): record for record in records.get("states", ())}
    if (
        not commands
        or int(commands[0]["version"]) != 1
        or commands[0].get("command_type") != "create_game"
    ):
        return _structural_mismatch(
            game_id,
            checked_versions,
            1,
            expected="replay format version 2 create command",
            actual="unsupported replay format",
        )
    try:
        create_payload = _mapping(commands[0].get("payload"))
        genesis = _mapping(create_payload.get("replay"))
        format_version = int(genesis.get("format_version", 0))
    except (TypeError, ValueError):
        format_version = 0
        genesis = {}
    if format_version != 2:
        return _structural_mismatch(
            game_id,
            checked_versions,
            1,
            expected="replay format version 2",
            actual="unsupported replay format",
        )
    try:
        setup_document = GameSetupDocument.model_validate(genesis["setup_document"])
        setup_payload = setup_document.model_dump(mode="json")
        if checksum_payload(setup_payload) != str(genesis["setup_checksum"]):
            raise ValueError("setup checksum mismatch")
        mechanics = setup_document.mechanics
        if checksum_payload(mechanics.model_dump(mode="json")) != str(
            genesis["mechanics_checksum"]
        ):
            raise ValueError("mechanics checksum mismatch")
        definition = rule_definition_from_values(
            player_count=sum(mechanics.role_counts.values()),
            role_counts=mechanics.role_counts,
            rules=mechanics.rules.model_dump(mode="json"),
            roles={
                role_id: role.model_dump(mode="json") for role_id, role in mechanics.roles.items()
            },
            abilities={
                ability_id: ability.model_dump(mode="json")
                for ability_id, ability in mechanics.abilities.items()
            },
            composition=mechanics.composition.model_dump(mode="json"),
        )
        rules = RuleRegistry.standard().build(definition)
        setup = game_setup_from_data({"players": genesis["players"]})
        seed = _optional_int(genesis.get("seed"))
        game = Game.create(setup, rules=rules, random=random.Random(seed))
    except (KeyError, TypeError, ValueError):
        return _structural_mismatch(
            game_id,
            checked_versions,
            1,
            expected="valid replay genesis",
            actual="invalid replay genesis",
        )

    generated_events = list(game.creation_events)
    mismatch = _compare_replayed_version(
        game_id,
        1,
        game,
        generated_events,
        states,
        records,
        checked_versions,
        seed,
    )
    if mismatch is not None:
        return mismatch

    for command in commands[1:]:
        version = int(command["version"])
        payload = _mapping(command.get("payload"))
        generated_events = []
        try:
            if command.get("command_type") == "submit_action":
                request = dict(_mapping(payload.get("request")))
                request["player_id"] = payload.get("player_id")
                generated_events.extend(game.submit(action_from_data(request)))
            elif command.get("command_type") == "advance_game":
                for action_data in _sequence(payload.get("domain_actions")):
                    generated_events.extend(game.submit(action_from_data(_mapping(action_data))))
                generated_events.extend(
                    game.advance(random.Random(runtime_seed(seed, version - 1)))
                )
            else:
                raise ValueError("unsupported command")
        except (KeyError, TypeError, ValueError):
            return _structural_mismatch(
                game_id,
                checked_versions,
                version,
                expected="supported deterministic command",
                actual="invalid replay command",
            )
        mismatch = _compare_replayed_version(
            game_id,
            version,
            game,
            generated_events,
            states,
            records,
            checked_versions,
            seed,
        )
        if mismatch is not None:
            return mismatch
    return None


def _compare_replayed_version(
    game_id: str,
    version: int,
    game: Game,
    generated_events: Sequence[object],
    states: Mapping[int, Mapping[str, Any]],
    records: Mapping[str, Sequence[Mapping[str, Any]]],
    checked_versions: set[int],
    seed: int | None,
) -> ReplayVerificationResult | None:
    state_record = states.get(version)
    if state_record is None:
        return _structural_mismatch(
            game_id,
            checked_versions,
            version,
            expected="persisted state version",
            actual="missing state version",
        )
    payload = _mapping(state_record["payload"])
    expected_private = payload.get("private_state")
    actual_private = domain_to_data(game.snapshot())
    if checksum_payload(expected_private) != checksum_payload(actual_private):
        return ReplayVerificationResult(
            game_id=game_id,
            valid=False,
            checked_versions=len(checked_versions),
            first_mismatch_version=version,
            comparison_target="private_state",
            expected_checksum=checksum_payload(expected_private),
            actual_checksum=checksum_payload(actual_private),
        )
    expected_public = _mapping(payload.get("public_state"))
    actual_public = public_state_payload_from_snapshot(
        game.snapshot(),
        game_id=game_id,
        version=version,
        seed=seed,
        created_at=expected_public.get("created_at"),
        scenario_id=_optional_text(expected_public.get("scenario_id")),
        scenario_name=_optional_text(expected_public.get("scenario_name")),
        narration_mode=str(expected_public.get("narration_mode") or "standard"),
        theme=_mapping(expected_public["theme"]) if expected_public.get("theme") else None,
    )
    if checksum_payload(expected_public) != checksum_payload(actual_public):
        return ReplayVerificationResult(
            game_id=game_id,
            valid=False,
            checked_versions=len(checked_versions),
            first_mismatch_version=version,
            comparison_target="public_projection",
            expected_checksum=checksum_payload(expected_public),
            actual_checksum=checksum_payload(actual_public),
        )
    expected_events = [
        _stored_event(record)
        for record in records.get("events", ())
        if int(record["version"]) == version and record.get("event_type") != "state_committed"
    ]
    actual_events = [_generated_event(event) for event in generated_events]
    if checksum_payload(expected_events) != checksum_payload(actual_events):
        return ReplayVerificationResult(
            game_id=game_id,
            valid=False,
            checked_versions=len(checked_versions),
            first_mismatch_version=version,
            comparison_target="events",
            expected_checksum=checksum_payload(expected_events),
            actual_checksum=checksum_payload(actual_events),
        )
    return None


def _stored_event(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(_mapping(record.get("payload")))
    payload.pop("narration", None)
    return {
        "visibility": record.get("visibility"),
        "phase": record.get("phase"),
        "day": record.get("day"),
        "actor_id": record.get("actor_id"),
        "event_type": record.get("event_type"),
        "payload": payload,
    }


def _generated_event(event: object) -> dict[str, Any]:
    created = event_to_create(event, narration_mode="none")  # type: ignore[arg-type]
    return created.model_dump(mode="json")


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("replay payload must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("replay payload must be an array")
    return cast(Sequence[Any], value)


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
        snapshot = game_state_from_data(private_state)
        rebuilt = public_state_payload_from_snapshot(
            snapshot,
            game_id=game_id,
            version=version,
            seed=_optional_int(public_state.get("seed")),
            created_at=public_state.get("created_at"),
            scenario_id=_optional_text(public_state.get("scenario_id")),
            scenario_name=_optional_text(public_state.get("scenario_name")),
            narration_mode=str(public_state.get("narration_mode") or "standard"),
            theme=_mapping(public_state["theme"]) if public_state.get("theme") else None,
        )
    except (TypeError, ValueError):
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
        comparison_target="public_projection",
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
    target: str = "structure",
) -> ReplayVerificationResult:
    return ReplayVerificationResult(
        game_id=game_id,
        valid=False,
        checked_versions=len(checked_versions),
        first_mismatch_version=max(version, 1),
        comparison_target=target,
        expected_checksum=checksum_payload(expected),
        actual_checksum=checksum_payload(actual),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


__all__ = ["ReplayRepository", "checksum_payload", "verify_replay"]
