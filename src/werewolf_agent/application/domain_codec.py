"""Serialization boundary between immutable domain values and persistence data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, cast

from werewolf_agent.domain.state import (
    AbilityDefinition,
    Action,
    ActionType,
    DiscussionConfig,
    DiscussionKind,
    DiscussionResult,
    DiscussionRound,
    DiscussionRoundKind,
    GameConfig,
    GameHistory,
    GameSetup,
    GameState,
    InspectionResult,
    LifecycleConfig,
    NightConfig,
    NightResult,
    PendingActions,
    Phase,
    Player,
    PlayerStatus,
    RoleCatalog,
    RoleDefinition,
    SpeechAct,
    SpeechRecord,
    SubmissionMode,
    VoteResult,
    VotingConfig,
    WinResult,
)


def domain_to_data(value: Any) -> Any:
    """Convert a domain value to JSON-compatible Python data."""
    if isinstance(value, Action):
        result: dict[str, Any] = {"player_id": value.player_id, "type": value.type.value}
        for field_name in (
            "ability_id",
            "target_id",
            "message",
            "speech_act",
            "subject_id",
            "evidence_id",
            "response_to_id",
        ):
            item = getattr(value, field_name)
            if item is not None:
                result[field_name] = item
        if value.reason:
            result["reason"] = value.reason
        return result
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: domain_to_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key.value if isinstance(key, Enum) else key): domain_to_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [domain_to_data(item) for item in value]
    return value


def game_setup_from_data(data: Mapping[str, Any]) -> GameSetup:
    """Build validated setup values from an application payload."""
    return GameSetup(players=tuple(_player(item) for item in _sequence(data.get("players"))))


def action_from_data(data: Mapping[str, Any]) -> Action:
    """Build one validated domain action from an application payload."""
    action_type = ActionType(str(data["type"]))
    player_id = str(data["player_id"])
    if action_type is ActionType.SPEECH:
        return Action.speech(
            player_id,
            str(data["message"]),
            speech_act=SpeechAct(str(data["speech_act"])),
            subject_id=str(data["subject_id"]),
            evidence_id=_optional_text(data.get("evidence_id")),
            response_to_id=_optional_text(data.get("response_to_id")),
        )
    if action_type is ActionType.VOTE:
        return Action.vote(
            player_id,
            str(data["target_id"]),
            reason=str(data["reason"]),
            evidence_id=_optional_text(data.get("evidence_id")),
        )
    if action_type is ActionType.USE_ABILITY:
        return Action.use_ability(
            player_id,
            str(data["ability_id"]),
            _optional_text(data.get("target_id")),
        )
    return Action.pass_(player_id)


def game_state_from_data(data: Mapping[str, Any]) -> GameState:
    """Build a validated immutable aggregate snapshot from persistence data."""
    config = _mapping(data["config"])
    players = _mapping(data["players"])
    return GameState(
        config=game_config_from_data(config),
        phase=Phase(str(data["phase"])),
        day=int(data["day"]),
        players={str(key): _player(value) for key, value in players.items()},
        history=_history(_mapping(data.get("history", {}))),
        pending_actions=_pending(_mapping(data.get("pending_actions", {}))),
        ability_uses={
            str(player_id): {
                str(ability_id): int(count) for ability_id, count in _mapping(uses).items()
            }
            for player_id, uses in _mapping(data.get("ability_uses", {})).items()
        },
        win_result=_win(data.get("win_result")),
    )


def game_config_from_data(data: Mapping[str, Any]) -> GameConfig:
    """Build validated domain configuration from persistence data."""
    roles_data = _mapping(_mapping(data["roles"])["roles"])
    abilities_data = _mapping(data["abilities"])
    return GameConfig(
        player_count=int(data["player_count"]),
        role_counts={str(key): int(value) for key, value in _mapping(data["role_counts"]).items()},
        discussion=DiscussionConfig(
            kind=DiscussionKind(str(_mapping(data["discussion"])["kind"])),
            message_max_chars=int(_mapping(data["discussion"])["message_max_chars"]),
            cycles_per_day=int(_mapping(data["discussion"])["cycles_per_day"]),
        ),
        voting=VotingConfig(**dict(_mapping(data["voting"]))),
        night=NightConfig(**dict(_mapping(data["night"]))),
        lifecycle=LifecycleConfig(**dict(_mapping(data["lifecycle"]))),
        roles=RoleCatalog(
            roles={
                str(key): RoleDefinition(
                    identity_faction=str(_mapping(value)["identity_faction"]),
                    victory_team=str(_mapping(value)["victory_team"]),
                    abilities=tuple(
                        str(item) for item in _sequence(_mapping(value).get("abilities"))
                    ),
                )
                for key, value in roles_data.items()
            }
        ),
        abilities={
            str(key): AbilityDefinition(
                kind=str(_mapping(value)["kind"]),
                phase=Phase(str(_mapping(value)["phase"])),
                target_policy=str(_mapping(value)["target_policy"]),
                start_day=int(_mapping(value)["start_day"]),
                max_uses=_optional_int(_mapping(value).get("max_uses")),
                result_visibility=str(_mapping(value)["result_visibility"]),
                resolution_priority=int(_mapping(value)["resolution_priority"]),
                allow_repeat_target=bool(_mapping(value)["allow_repeat_target"]),
                enabled_first_night=bool(_mapping(value)["enabled_first_night"]),
                result_detail=_optional_text(_mapping(value).get("result_detail")),
                knowledge_mode=_optional_text(_mapping(value).get("knowledge_mode")),
                tie_resolution=_optional_text(_mapping(value).get("tie_resolution")),
                source_kinds=tuple(
                    str(item) for item in _sequence(_mapping(value).get("source_kinds"))
                ),
            )
            for key, value in abilities_data.items()
        },
        phase_order=tuple(Phase(str(value)) for value in _sequence(data.get("phase_order"))),
    )


def _player(value: Any) -> Player:
    data = _mapping(value)
    return Player(
        id=str(data["id"]),
        name=str(data["name"]),
        role=_optional_text(data.get("role")),
        status=PlayerStatus(str(data.get("status", PlayerStatus.ALIVE.value))),
        eliminated_day=_optional_int(data.get("eliminated_day")),
        killed_night=_optional_int(data.get("killed_night")),
    )


def _history(data: Mapping[str, Any]) -> GameHistory:
    return GameHistory(
        speeches=tuple(
            SpeechRecord(
                day=int(item["day"]),
                speech_id=str(item["speech_id"]),
                round_id=str(item["round_id"]),
                round_kind=DiscussionRoundKind(str(item["round_kind"])),
                player_id=str(item["player_id"]),
                message=str(item["message"]),
                speech_act=SpeechAct(str(item["speech_act"])),
                subject_id=str(item["subject_id"]),
                evidence_id=_optional_text(item.get("evidence_id")),
                response_to_id=_optional_text(item.get("response_to_id")),
            )
            for item in map(_mapping, _sequence(data.get("speeches")))
        ),
        discussions=tuple(
            DiscussionResult(
                day=int(item["day"]),
                round_id=str(item["round_id"]),
                kind=DiscussionRoundKind(str(item["kind"])),
                speech_ids=tuple(str(value) for value in _sequence(item.get("speech_ids"))),
            )
            for item in map(_mapping, _sequence(data.get("discussions")))
        ),
        votes=tuple(_vote(item) for item in map(_mapping, _sequence(data.get("votes")))),
        nights=tuple(_night(item) for item in map(_mapping, _sequence(data.get("nights")))),
    )


def _vote(data: Mapping[str, Any]) -> VoteResult:
    return VoteResult(
        day=int(data["day"]),
        tie_break_policy=str(data["tie_break_policy"]),
        votes={str(key): str(value) for key, value in _mapping(data.get("votes", {})).items()},
        reasons={str(key): str(value) for key, value in _mapping(data.get("reasons", {})).items()},
        evidence_ids={
            str(key): str(value) for key, value in _mapping(data.get("evidence_ids", {})).items()
        },
        counts={str(key): int(value) for key, value in _mapping(data.get("counts", {})).items()},
        tied_player_ids=tuple(str(value) for value in _sequence(data.get("tied_player_ids"))),
        missing_voter_ids=tuple(str(value) for value in _sequence(data.get("missing_voter_ids"))),
        eliminated_player_id=_optional_text(data.get("eliminated_player_id")),
        round=int(data.get("round") or 1),
        requires_revote=bool(data.get("requires_revote", False)),
    )


def _night(data: Mapping[str, Any]) -> NightResult:
    return NightResult(
        day=int(data["day"]),
        attacked_player_id=_optional_text(data.get("attacked_player_id")),
        protected_player_id=_optional_text(data.get("protected_player_id")),
        killed_player_id=_optional_text(data.get("killed_player_id")),
        killed_player_ids=tuple(str(value) for value in _sequence(data.get("killed_player_ids"))),
        inspections=tuple(
            InspectionResult(
                day=int(item["day"]),
                player_id=str(item["player_id"]),
                ability_id=str(item["ability_id"]),
                target_id=str(item["target_id"]),
                target_role=str(item["target_role"]),
                target_faction=str(item["target_faction"]),
            )
            for item in map(_mapping, _sequence(data.get("inspections")))
        ),
        ability_targets={
            str(player_id): {
                str(ability_id): str(target_id)
                for ability_id, target_id in _mapping(targets).items()
            }
            for player_id, targets in _mapping(data.get("ability_targets", {})).items()
        },
    )


def _pending(data: Mapping[str, Any]) -> PendingActions:
    return PendingActions(
        votes={
            str(key): action_from_data(_mapping(value))
            for key, value in _mapping(data.get("votes", {})).items()
        },
        night_actions={
            str(key): action_from_data(_mapping(value))
            for key, value in _mapping(data.get("night_actions", {})).items()
        },
        discussion_actions={
            str(key): action_from_data(_mapping(value))
            for key, value in _mapping(data.get("discussion_actions", {})).items()
        },
        discussion_round=_discussion_round(data.get("discussion_round")),
        vote_round=int(data.get("vote_round") or 1),
        revote_candidates=tuple(str(value) for value in _sequence(data.get("revote_candidates"))),
    )


def _discussion_round(value: Any) -> DiscussionRound | None:
    if value is None:
        return None
    data = _mapping(value)
    return DiscussionRound(
        round_id=str(data["round_id"]),
        cycle=int(data["cycle"]),
        kind=DiscussionRoundKind(str(data["kind"])),
        submission_mode=SubmissionMode(str(data["submission_mode"])),
        actor_order=tuple(str(item) for item in _sequence(data["actor_order"])),
        cursor=int(data.get("cursor") or 0),
        reference_ids=tuple(str(item) for item in _sequence(data.get("reference_ids"))),
    )


def _win(value: Any) -> WinResult | None:
    if value is None:
        return None
    data = _mapping(value)
    return WinResult(
        winner=str(data["winner"]),
        reason=str(data["reason"]),
        day=int(data["day"]),
        winning_player_ids=tuple(str(item) for item in _sequence(data["winning_player_ids"])),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("domain payload must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("domain payload must be an array")
    return cast(Sequence[Any], value)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


__all__ = [
    "action_from_data",
    "domain_to_data",
    "game_config_from_data",
    "game_setup_from_data",
    "game_state_from_data",
]
